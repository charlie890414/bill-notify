"""Pipeline - Workflow orchestration for bill processing"""

import logging
from datetime import datetime
from pathlib import Path
from bill_notify.models import (
    BillEmail,
    ProcessingSummary,
    BillAnalysisResult,
    CalendarEvent,
)
from bill_notify.gmail_fetcher import GmailFetcher
from bill_notify.pdf_processor import PDFProcessor
from bill_notify.llm_analyzer import LLMAnalyzer
from bill_notify.calendar_sync import CalendarSync
from bill_notify.interfaces import PasswordProvider
from bill_notify.google_services import GoogleServices
from bill_notify.constants import EVENT_SUMMARY_PREFIX, EVENT_SUMMARY_SUFFIX, PREFIXES_TO_REMOVE


logger = logging.getLogger(__name__)


class BillPipeline:
    """
    Orchestrates the complete bill processing workflow:
    1. Fetch emails from Gmail
    2. Process PDFs (decrypt, extract text)
    3. Analyze with LLM (extract due date)
    4. Create calendar events
    5. Mark emails as processed
    """

    def __init__(
        self,
        gmail: GmailFetcher,
        pdf_processor: PDFProcessor,
        llm_analyzer: LLMAnalyzer,
        calendar: CalendarSync,
        processed_log: Path,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.gmail = gmail
        self.pdf_processor = pdf_processor
        self.llm_analyzer = llm_analyzer
        self.calendar = calendar
        self.processed_log = Path(processed_log)
        self.dry_run = dry_run
        self.verbose = verbose

    async def run(self) -> ProcessingSummary:
        """
        Execute the complete workflow.
        Returns ProcessingSummary with counts and processed email IDs.
        """
        logger.info("=" * 60)
        logger.info("Bill Notification System Started")
        if self.dry_run:
            logger.info("Mode: DRY RUN (no changes will be made)")
        logger.info("=" * 60)

        # 1. Fetch emails
        logger.info("\n[1/4] Fetching PDF attachments from Gmail...")
        emails = self.gmail.fetch_pending()

        if not emails:
            logger.info("No new bills to process")
            return ProcessingSummary()

        logger.info(f"Found {len(emails)} emails to process")

        # 3. Pre-initialize OCR model if there are emails to process
        if emails:
            logger.info("Initializing OCR model...")
            _ = self.pdf_processor.ocr
            logger.info("OCR model ready")

        # 4. Process each email
        summary = ProcessingSummary()
        for email in emails:
            result = await self._process_email(email)
            self._update_summary(summary, result)

        # 3. Mark processed emails
        if not self.dry_run and summary.processed_emails:
            logger.info("\n[3/4] Marking emails as processed...")
            for msg_id in summary.processed_emails:
                self.gmail.mark_processed(msg_id)
            logger.info(f"Marked {len(summary.processed_emails)} emails as processed")
        elif self.dry_run:
            logger.info("\n[3/4] Dry run - emails NOT marked as processed")

        # 4. Summary
        logger.info("\n[4/4] Processing complete")
        logger.info("=" * 60)
        logger.info(f"Results: {summary.success_count} succeeded, {summary.skipped_count} skipped, {summary.failed_count} failed")
        logger.info("=" * 60)

        return summary

    async def _process_email(self, email: BillEmail) -> BillAnalysisResult:
        """Process a single email through the pipeline"""
        if self.verbose:
            logger.info(f"\nProcessing: {email.pdf_path.name}")
            logger.info(f"  Sender: {email.sender}")
            logger.info(f"  Subject: {email.subject}")

        # Step 1: Extract text from PDF
        if self.verbose:
            logger.info("  Extracting text from PDF...")
        try:
            pdf_text = self.pdf_processor.process_pdf(email.pdf_path, email.sender)
        except Exception as e:
            logger.error(f"  PDF processing failed: {e}")
            return BillAnalysisResult(status="failed", error=str(e))

        # Step 2: Analyze with LLM
        if self.verbose:
            logger.info("  Analyzing with LLM...")
        result = await self.llm_analyzer.analyze_pdf(pdf_text, email.subject)

        # Update bill source with correct msg_id
        if result.bill and not result.bill.source.msg_id:
            result.bill.source.msg_id = email.msg_id

        if result.status == "not_bill":
            logger.info("  Document is not a bill requiring payment")
            # Mark as processed (skip)
            return result

        if result.status == "failed":
            logger.warning(f"  Analysis failed: {result.error}")
            return result

        # Step 3: Check if expired
        bill = result.bill
        if bill and bill.is_expired:
            logger.warning(f"  Due date {bill.due_date} has passed, skipping")
            return BillAnalysisResult(status="not_bill", bill=bill, error="Expired bill")

        # Step 4: Check for duplicates
        if bill and self.calendar.check_event_exists(bill):
            logger.warning("  Similar event already exists, skipping")
            return BillAnalysisResult(status="not_bill", bill=bill, error="Duplicate event")

        # Step 5: Create calendar event
        if bill:
            event = self._build_event(bill)
            if self.dry_run:
                logger.info(f"  [DRY RUN] Would create: {event.summary} on {event.due_date}")
                return result
            else:
                try:
                    event_id = self.calendar.create_event(event)
                    logger.info(f"  Created calendar event (ID: {event_id})")
                    return result
                except Exception as e:
                    logger.error(f"  Failed to create event: {e}")
                    return BillAnalysisResult(status="failed", bill=bill, error=str(e))

        return result

    def _build_event(self, bill) -> CalendarEvent:
        """Build calendar event from extracted bill"""
        from bill_notify.models import ExtractedBill
        if not isinstance(bill, ExtractedBill):
            raise ValueError("Expected ExtractedBill")

        # Build summary: prioritize LLM summary, then clean subject, then filename
        summary = bill.summary
        if not summary:
            summary = self._clean_subject(bill.source.subject)

        if not summary:
            summary = bill.source.pdf_path.stem

        summary = f"{EVENT_SUMMARY_PREFIX} {summary} {EVENT_SUMMARY_SUFFIX}"

        # Build description
        description = "Automatically created bill reminder\n"
        description += f"Source: {bill.source.pdf_path.name}\n"
        description += f"Email Subject: {bill.source.subject}\n"
        description += f"Extracted: {datetime.now().date()}"
        if bill.amount:
            description += f"\nAmount: {bill.amount}"

        return CalendarEvent(
            summary=summary,
            due_date=bill.due_date,
            description=description,
        )

    def _clean_subject(self, subject: str) -> str:
        """Remove bill-related prefixes from subject"""
        cleaned = subject.strip()
        lower = cleaned.lower()

        for prefix in PREFIXES_TO_REMOVE:
            if lower.startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()
                break

        return cleaned

    def _update_summary(
        self, summary: ProcessingSummary, result: BillAnalysisResult
    ):
        """Update summary based on analysis result"""
        if result.status == "success":
            summary.success_count += 1
            if result.bill and result.bill.source.msg_id:
                summary.processed_emails.append(result.bill.source.msg_id)
        elif result.status == "not_bill":
            summary.skipped_count += 1
            if result.bill and result.bill.source.msg_id:
                summary.processed_emails.append(result.bill.source.msg_id)
        else:  # failed
            summary.failed_count += 1


def create_pipeline(
    google_services: GoogleServices,
    password_provider: PasswordProvider,
    llm_api_key: str,
    llm_model: str,
    download_dir: Path,
    processed_log: Path,
    calendar_id: str,
    reminder_days: int,
    gmail_label: str = "bills",
    days_back: int = 7,
    dry_run: bool = False,
    verbose: bool = False,
) -> BillPipeline:
    """Factory function to create a fully configured pipeline"""
    gmail = GmailFetcher(
        gmail_service=google_services.gmail_provider(),
        download_dir=download_dir,
        processed_log=processed_log,
        label=gmail_label,
        days_back=days_back,
    )
    pdf_processor = PDFProcessor(password_provider=password_provider)
    llm_analyzer = LLMAnalyzer(api_key=llm_api_key, model=llm_model)
    calendar = CalendarSync(
        calendar_service=google_services.calendar_provider(),
        calendar_id=calendar_id,
        reminder_days=reminder_days,
    )

    return BillPipeline(
        gmail=gmail,
        pdf_processor=pdf_processor,
        llm_analyzer=llm_analyzer,
        calendar=calendar,
        processed_log=processed_log,
        dry_run=dry_run,
        verbose=verbose,
    )