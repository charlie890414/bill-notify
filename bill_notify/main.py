"""Main program - Bill notification system"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from bill_notify.config import AppConfig
from bill_notify.gmail_fetcher import GmailFetcher
from bill_notify.pdf_processor import PDFProcessor
from bill_notify.llm_analyzer import LLMAnalyzer
from bill_notify.calendar_sync import CalendarSync


class BillNotify:
    """Bill notification main program"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.gmail_fetcher = GmailFetcher(config)
        self.pdf_processor = PDFProcessor()
        self.llm_analyzer = LLMAnalyzer(config)
        self.calendar_sync = CalendarSync(config)

    async def process_single_pdf(self, pdf_path: Path) -> Optional[date]:
        """
        Process a single PDF file, extract due date and create calendar event
        Returns:
            Due date if successful
        """
        print(f"\nProcessing file: {pdf_path.name}")

        try:
            # 1. PDF to images
            print("  Converting PDF to images...")
            base64_images = self.pdf_processor.process_pdf(pdf_path)

            # 2. LLM analysis to extract due date
            print("  Using LLM to analyze due date...")
            due_date = await self.llm_analyzer.analyze_pdf(base64_images)

            if due_date is None:
                print(f"  ⚠️  Could not extract due date from {pdf_path.name}")
                return None

            print(f"  ✓  Extracted due date: {due_date}")

            # Check if already expired
            today = datetime.now().date()
            if due_date < today:
                print(f"  ⚠️  Due date {due_date} has passed, skipping event creation")
                return due_date

            # 3. Check if similar event already exists
            summary_keywords = ["bill", "payment", "due"]
            if self.calendar_sync.check_event_exists(due_date, summary_keywords):
                print(f"  ⚠️  Similar event already exists on {due_date}, skipping")
                return due_date

            # 4. Create calendar event
            event_summary = f"[Bill] {pdf_path.stem} - Payment Due"
            event_description = f"Automatically created bill reminder\nSource: {pdf_path.name}\nExtracted: {today}"

            event_id = self.calendar_sync.create_event(
                summary=event_summary,
                due_date=due_date,
                description=event_description,
                reminder_days=self.config.calendar.reminder_days,
            )
            print(f"  ✓  Created calendar event (ID: {event_id})")

            return due_date

        except Exception as e:
            print(f"  ✗  Processing failed: {e}")
            return None

    async def run(self):
        """
        Main workflow
        1. Fetch PDF attachments from unread emails in Gmail
        2. Process each PDF to extract due date
        3. Create calendar reminders
        """
        print("=" * 60)
        print("Bill Notification System Started")
        print(f"Config: Label={self.config.gmail.gmail_label}, Reminder={self.config.calendar.reminder_days} days in advance")
        print("=" * 60)

        # 1. Download PDFs from Gmail
        print("\n[1/3] Fetching PDF attachments from Gmail...")
        pdf_files = self.gmail_fetcher.process_emails()
        print(f"  Downloaded {len(pdf_files)} PDF files")

        if not pdf_files:
            print("  No new bills to process")
            return

        # 2. Process each PDF
        print("\n[2/3] Analyzing PDFs to extract due dates...")
        processed_count = 0
        skipped_count = 0

        for pdf_path in pdf_files:
            due_date = await self.process_single_pdf(pdf_path)
            if due_date:
                processed_count += 1
            else:
                skipped_count += 1

        # 3. Summary
        print("\n" + "=" * 60)
        print(f"Processing complete: {processed_count} succeeded, {skipped_count} skipped")
        print("=" * 60)


async def main():
    """Program entry point"""
    try:
        config = AppConfig.load()
        notifier = BillNotify(config)
        await notifier.run()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
