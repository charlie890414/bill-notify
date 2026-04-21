"""Main program - Bill notification system"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, date
from typing import Tuple, Union, Literal
from bill_notify.config import AppConfig
from bill_notify.gmail_fetcher import GmailFetcher
from bill_notify.pdf_processor import PDFProcessor
from bill_notify.llm_analyzer import LLMAnalyzer
from bill_notify.calendar_sync import CalendarSync
from bill_notify.exceptions import (
    GmailError,
    CalendarError,
    PDFProcessingError,
    LLMAnalysisError,
)


logger = logging.getLogger(__name__)


class BillNotify:
    """Bill notification main program"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.gmail_fetcher = GmailFetcher(config)
        self.pdf_processor = PDFProcessor(pdf_passwords=config.pdf_passwords)
        self.llm_analyzer = LLMAnalyzer(config)
        self.calendar_sync = CalendarSync(config)

    async def process_single_pdf(
        self, pdf_path: Path, sender_email: str = "", email_subject: str = ""
    ) -> Union[date, Literal[False], None]:
        """
        Process a single PDF file, extract due date and create calendar event
        Returns:
            Due date (date) if successful and event created
            False (Literal[False]) if document is not a bill requiring payment (but should be marked as processed)
            None if extraction failed or other error (should not be marked as processed)
        """
        if self.config.verbose:
            logger.info(f"\nProcessing file: {pdf_path.name}")
            if sender_email:
                logger.info(f"  Sender: {sender_email}")
            if email_subject:
                logger.info(f"  Subject: {email_subject}")

        try:
            # 1. Process PDF (decrypt if needed, encode to base64)
            if self.config.verbose:
                logger.info("Processing PDF...")
            pdf_context = self.pdf_processor.process_pdf(pdf_path, sender_email)

            # 2. LLM analysis to extract due date, amount, and event summary
            if self.config.verbose:
                logger.info("Using LLM to analyze due date...")
            result = await self.llm_analyzer.analyze_pdf(pdf_context, email_subject)
            due_date, llm_summary, amount = result

            # Handle NOT_BILL case: document is not a bill requiring payment
            if due_date is False:
                logger.info(
                    f"Document {pdf_path.name} is not a bill requiring payment, skipping"
                )
                return False

            # Handle EXTRACTION_FAILED or other None case
            if due_date is None:
                logger.warning(f"Could not extract due date from {pdf_path.name}")
                return None

            # Type narrowing: due_date must be a date object here (not False, not None)
            assert isinstance(due_date, date)
            logger.info(f"Extracted due date: {due_date}")
            if amount:
                logger.info(f"Extracted amount: {amount}")

            # Check if already expired
            today = datetime.now().date()
            if due_date < today:
                logger.warning(
                    f"Due date {due_date} has passed, skipping event creation"
                )
                return due_date

            # 3. Check if similar event already exists from the same sender/file
            summary_keywords = ["bill", "payment", "due"]
            if self.calendar_sync.check_event_exists(
                due_date,
                summary_keywords,
                sender_email=sender_email,
                pdf_filename=pdf_path.name,
            ):
                logger.warning(
                    f"Similar event from this sender/file already exists on {due_date}, skipping"
                )
                return due_date

            # 4. Create calendar event - prioritize LLM-generated summary, then email subject, then filename
            if llm_summary:
                event_summary = f"[Bill] {llm_summary} - Payment Due"
            elif email_subject:
                event_title = email_subject.strip()
                prefixes_to_remove = ["[Bill]", "Bill:", "Invoice:", "Payment:"]
                lower_title = event_title.lower()
                for prefix in prefixes_to_remove:
                    if lower_title.startswith(prefix.lower()):
                        event_title = event_title[len(prefix) :].strip()
                        break
                event_summary = f"[Bill] {event_title} - Payment Due"
            else:
                event_summary = f"[Bill] {pdf_path.stem} - Payment Due"

            # Build event description with amount if available
            amount_info = f"\nAmount: {amount}" if amount else ""
            event_description = f"Automatically created bill reminder\nSource: {pdf_path.name}\nEmail Subject: {email_subject or 'N/A'}\nExtracted: {today}{amount_info}"

            # Skip event creation in dry-run mode
            if self.config.dry_run:
                logger.info(
                    f"[DRY RUN] Would create calendar event: {event_summary} on {due_date}"
                )
                if amount:
                    logger.info(f"[DRY RUN] Amount: {amount}")
                return due_date

            event_id = self.calendar_sync.create_event(
                summary=event_summary,
                due_date=due_date,
                description=event_description,
                reminder_days=self.config.calendar.reminder_days,
            )
            logger.info(f"Created calendar event (ID: {event_id})")

            return due_date

        except GmailError as e:
            logger.error(f"Gmail operation failed: {e}")
            if e.original_error:
                logger.debug(f"Original error: {e.original_error}", exc_info=True)
            return None
        except CalendarError as e:
            logger.error(f"Calendar operation failed: {e}")
            if e.original_error:
                logger.debug(f"Original error: {e.original_error}", exc_info=True)
            return None
        except PDFProcessingError as e:
            logger.error(f"PDF processing failed: {e}")
            if e.original_error:
                logger.debug(f"Original error: {e.original_error}", exc_info=True)
            return None
        except LLMAnalysisError as e:
            logger.error(f"LLM analysis failed: {e}")
            if e.original_error:
                logger.debug(f"Original error: {e.original_error}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            return None

    async def run(self) -> Tuple[int, int]:
        """
        Main workflow
        1. Fetch PDF attachments from unread emails in Gmail
        2. Process each PDF to extract due date
        3. Create calendar reminders
        Returns:
            Tuple of (processed_count, skipped_count)
        """
        logger.info("=" * 60)
        logger.info("Bill Notification System Started")
        logger.info(
            f"Config: Label={self.config.gmail.gmail_label}, Reminder={self.config.calendar.reminder_days} days in advance, Days back={self.config.gmail.days_back}"
        )
        if self.config.dry_run:
            logger.info("Mode: DRY RUN (no changes will be made)")
        logger.info("=" * 60)

        # 1. Download PDFs from Gmail
        logger.info("\n[1/3] Fetching PDF attachments from Gmail...")
        try:
            pdf_files = self.gmail_fetcher.process_emails()
        except GmailError as e:
            logger.error(f"Failed to fetch emails from Gmail: {e}")
            if e.original_error:
                logger.debug(f"Original error: {e.original_error}", exc_info=True)
            return 0, 0
        logger.info(f"Downloaded {len(pdf_files)} PDF files")

        if not pdf_files:
            logger.info("No new bills to process")
            return 0, 0

        # 2. Process each PDF
        logger.info("\n[2/3] Analyzing PDFs to extract due dates...")
        processed_count = 0
        skipped_count = 0
        successful_emails = []  # Track (msg_id, pdf_path) that succeeded

        for msg_id, pdf_path, sender_email, email_subject in pdf_files:
            result = await self.process_single_pdf(
                pdf_path, sender_email, email_subject
            )
            # result can be: date (success), False (not a bill), or None (extraction failed)
            if result is not False and result is not None:
                # date - success
                processed_count += 1
                successful_emails.append((msg_id, pdf_path))
            elif result is False:
                # False (not a bill) count as skipped
                skipped_count += 1
                successful_emails.append((msg_id, pdf_path))
            else:
                # None (extraction failed) count as skipped
                skipped_count += 1

        # 3. Mark emails as processed only if not in dry-run mode and event was created
        if not self.config.dry_run and successful_emails:
            logger.info("\n[3/3] Marking emails as processed...")
            try:
                for msg_id, pdf_path in successful_emails:
                    self.gmail_fetcher.mark_processed(msg_id)
                logger.info(f"Marked {len(successful_emails)} emails as processed")
            except GmailError as e:
                logger.error(f"Failed to mark emails as processed: {e}")
                # Continue - emails will be retried on next run
        elif self.config.dry_run:
            logger.info("\n[3/3] Dry run mode - emails NOT marked as processed")

        # 4. Summary
        logger.info("\n" + "=" * 60)
        logger.info(
            f"Processing complete: {processed_count} succeeded, {skipped_count} skipped"
        )
        logger.info("=" * 60)

        return processed_count, skipped_count


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Bill notification system - fetch bills from Gmail and create calendar reminders"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating calendar events or marking emails as processed",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--config", type=str, help="Path to config file (overrides default)"
    )
    parser.add_argument(
        "--label", type=str, help="Gmail label to filter (overrides config)"
    )
    parser.add_argument(
        "--reminder-days", type=int, help="Reminder days in advance (overrides config)"
    )
    parser.add_argument(
        "--calendar-id", type=str, help="Calendar ID (overrides config)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        help="Number of days to look back for emails (overrides config)",
    )
    return parser.parse_args()


async def main():
    """Program entry point"""
    try:
        args = parse_args()

        # Configure logging
        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True,
        )

        config = AppConfig.load(
            dry_run=args.dry_run,
            verbose=args.verbose,
            config_file=args.config,
            label=args.label,
            reminder_days=args.reminder_days,
            calendar_id=args.calendar_id,
            days_back=args.days_back,
        )
        notifier = BillNotify(config)
        await notifier.run()
    except ValueError as e:
        logger.exception(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"File error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        sys.exit(1)


def cli():
    """CLI entry point for console script"""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
