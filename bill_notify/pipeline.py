"""Pipeline - Workflow orchestration for bill processing"""

import logging
from pathlib import Path
from typing import Optional
from bill_notify.models import (
    BillEmail,
    ProcessingSummary,
    BillAnalysisResult,
    CalendarEvent,
    ExtractedBill,
    ProcessedRecord,
)
from bill_notify.gmail_fetcher import GmailFetcher
from bill_notify.pdf_processor import PDFProcessor
from bill_notify.llm_analyzer import LLMAnalyzer
from bill_notify.calendar_sync import CalendarSync
from bill_notify.interfaces import PasswordProvider
from bill_notify.google_services import GoogleServices
from bill_notify.event_builder import build_calendar_event


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
        reminder_days: int | list[int] = 3,
        dry_run: bool = False,
        verbose: bool = False,
        force_reprocess: bool = False,
    ):
        self.gmail = gmail
        self.pdf_processor = pdf_processor
        self.llm_analyzer = llm_analyzer
        self.calendar = calendar
        self.processed_log = Path(processed_log)
        self.reminder_days = reminder_days
        self.dry_run = dry_run
        self.verbose = verbose
        self.force_reprocess = force_reprocess

    async def run(self) -> ProcessingSummary:
        """
        Execute the complete workflow.
        Returns ProcessingSummary with counts and processed email IDs.
        """
        logger.info("=" * 60)
        logger.info("Bill Notification System Started")
        if self.dry_run:
            logger.info("Mode: DRY RUN (no changes will be made)")
        if self.force_reprocess:
            logger.info("Mode: FORCE REPROCESS (processed log will be overwritten)")
        logger.info("=" * 60)

        # 1. Fetch emails
        logger.info("\n[1/4] Fetching PDF attachments from Gmail...")
        emails = self.gmail.fetch_pending()

        if not emails:
            logger.info("No new bills to process")
            return ProcessingSummary()

        logger.info(f"Found {len(emails)} emails to process")

        if self.force_reprocess:
            self._delete_previous_events(emails)

        # 3. Pre-initialize OCR model if there are emails to process
        if emails:
            logger.info("Initializing OCR model...")
            _ = self.pdf_processor.ocr
            logger.info("OCR model ready")

        # 4. Process each email
        summary = ProcessingSummary()
        for email in emails:
            result = await self._process_email(email)
            self._update_summary(summary, result, email)

        # 3. Mark processed emails
        if not self.dry_run and self.force_reprocess:
            logger.info("\n[3/4] Overwriting processed email records...")
            self.gmail.replace_processed(summary.processed_records)
            logger.info(
                f"Wrote {len(summary.processed_records)} processed email records"
            )
        elif not self.dry_run and summary.processed_emails:
            logger.info("\n[3/4] Marking emails as processed...")
            for record in summary.processed_records:
                self.gmail.mark_processed_record(record)
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
        result = await self.llm_analyzer.analyze_pdf(
            pdf_text, email.subject, email.sender
        )

        if result.status == "not_bill":
            logger.info("  Document is not a bill requiring payment")
            # Mark as processed (skip)
            return result

        if result.status == "failed":
            logger.warning(f"  Analysis failed: {result.error}")
            return result

        if not result.bill:
            logger.warning("  Analysis succeeded without bill details")
            return BillAnalysisResult(
                status="failed", error="Analysis succeeded without bill details"
            )

        result.bill.source = email

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
                    result.event_id = event_id
                    return result
                except Exception as e:
                    logger.error(f"  Failed to create event: {e}")
                    return BillAnalysisResult(status="failed", bill=bill, error=str(e))

        return result

    def _build_event(self, bill: ExtractedBill) -> CalendarEvent:
        """Build calendar event from extracted bill"""
        if not isinstance(bill, ExtractedBill):
            raise ValueError("Expected ExtractedBill")
        if bill.source is None:
            raise ValueError("ExtractedBill.source is required")

        return build_calendar_event(bill, self.reminder_days)

    def _update_summary(
        self, summary: ProcessingSummary, result: BillAnalysisResult, email: BillEmail
    ):
        """Update summary based on analysis result"""
        if result.status == "success":
            summary.success_count += 1
            summary.processed_emails.append(email.processed_key)
            summary.processed_records.append(
                ProcessedRecord.from_email_result(email, result)
            )
        elif result.status == "not_bill":
            summary.skipped_count += 1
            summary.processed_emails.append(email.processed_key)
            summary.processed_records.append(
                ProcessedRecord.from_email_result(email, result)
            )
        else:  # failed
            summary.failed_count += 1

    def _delete_previous_events(self, emails: list[BillEmail]) -> None:
        """Delete previously created calendar events for forced reprocessing."""
        processed_keys = [email.processed_key for email in emails]
        event_ids = self.gmail.event_ids_for_processed_keys(processed_keys)
        if not event_ids:
            return

        logger.info(f"Deleting {len(event_ids)} previous calendar events...")
        for event_id in event_ids:
            try:
                self.calendar.delete_event(event_id)
            except Exception as e:
                logger.warning(f"Failed to delete previous event {event_id}: {e}")


def create_pipeline(
    google_services: GoogleServices,
    password_provider: PasswordProvider,
    llm_api_key: str,
    llm_model: str,
    download_dir: Path,
    processed_log: Path,
    ocr_cache_dir: Path,
    calendar_id: str,
    reminder_days: int | list[int],
    gmail_label: str = "bills",
    days_back: int = 7,
    dry_run: bool = False,
    verbose: bool = False,
    force_reprocess: bool = False,
    ocr_text_detection_model_name: Optional[str] = None,
    ocr_text_recognition_model_name: Optional[str] = None,
    ocr_cpu_threads: Optional[int] = None,
) -> BillPipeline:
    """Factory function to create a fully configured pipeline"""
    gmail = GmailFetcher(
        gmail_service=google_services.gmail_provider(),
        download_dir=download_dir,
        processed_log=processed_log,
        label=gmail_label,
        days_back=days_back,
        ignore_processed=force_reprocess,
    )
    pdf_processor = PDFProcessor(
        password_provider=password_provider,
        ocr_cache_dir=ocr_cache_dir,
        text_detection_model_name=ocr_text_detection_model_name,
        text_recognition_model_name=ocr_text_recognition_model_name,
        cpu_threads=ocr_cpu_threads,
    )
    llm_analyzer = LLMAnalyzer(api_key=llm_api_key, model=llm_model)
    calendar = CalendarSync(
        calendar_service=google_services.calendar_provider(),
        calendar_id=calendar_id,
        reminder_days=reminder_days,
        overwrite_existing=force_reprocess,
    )

    return BillPipeline(
        gmail=gmail,
        pdf_processor=pdf_processor,
        llm_analyzer=llm_analyzer,
        calendar=calendar,
        processed_log=processed_log,
        reminder_days=reminder_days,
        dry_run=dry_run,
        verbose=verbose,
        force_reprocess=force_reprocess,
    )
