"""Gmail email fetcher module"""

import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from googleapiclient.errors import HttpError
from mailparser import MailParser
from bill_notify.models import BillEmail, ProcessedRecord
from bill_notify.interfaces import GmailServiceProvider
from bill_notify.exceptions import GmailError


logger = logging.getLogger(__name__)


class GmailFetcher:
    """Gmail email fetcher - fetches emails with PDF attachments"""

    def __init__(
        self,
        gmail_service: GmailServiceProvider,
        download_dir: Path,
        processed_log: Path,
        label: str = "bills",
        days_back: int = 7,
        ignore_processed: bool = False,
    ):
        self._gmail = gmail_service
        self.download_dir = Path(download_dir)
        self.processed_log = Path(processed_log)
        self.label = label
        self.days_back = days_back
        self.ignore_processed = ignore_processed
        self._load_processed_emails()

    @property
    def service(self):
        """Get the Gmail service"""
        return self._gmail.gmail_service()

    def _load_processed_emails(self):
        """Load processed email IDs from log file"""
        self.processed_emails: set[str] = set()
        self.processed_records: dict[str, ProcessedRecord] = {}
        if self.processed_log.exists():
            with open(self.processed_log, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Skipping invalid processed log JSON line")
                            continue

                        key = data.get("key")
                        if not key:
                            continue

                        record = ProcessedRecord(
                            key=key,
                            status=data.get("status", "success"),
                            processed_at=data.get("processed_at", ""),
                            msg_id=data.get("msg_id", ""),
                            sender=data.get("sender", ""),
                            subject=data.get("subject", ""),
                            pdf_path=data.get("pdf_path", ""),
                            event_id=data.get("event_id"),
                            error=data.get("error"),
                        )
                        self.processed_records[key] = record
                        self.processed_emails.add(key)
                    else:
                        self.processed_emails.add(line)

    def _reload_processed_emails(self):
        """Reload processed emails from log file (for use after marking)"""
        self._load_processed_emails()

    def mark_processed(self, processed_key: str):
        """Mark an email or email attachment as processed"""
        self.processed_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.processed_log, "a", encoding="utf-8") as f:
            f.write(f"{processed_key}\n")
        self.processed_emails.add(processed_key)

    def mark_processed_record(self, record: ProcessedRecord):
        """Append a structured processed record."""
        self.processed_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.processed_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
        self.processed_emails.add(record.key)
        self.processed_records[record.key] = record

    def replace_processed(self, processed_records: list[ProcessedRecord] | list[str]):
        """Replace the processed log with the given processed records."""
        unique_records: dict[str, ProcessedRecord] = {}
        legacy_keys: list[str] = []
        for item in processed_records:
            if isinstance(item, ProcessedRecord):
                unique_records[item.key] = item
            else:
                legacy_keys.append(item)

        unique_keys = list(dict.fromkeys(legacy_keys))
        self.processed_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.processed_log, "w", encoding="utf-8") as f:
            for record in unique_records.values():
                f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
            for processed_key in unique_keys:
                f.write(f"{processed_key}\n")
        self.processed_records = unique_records
        self.processed_emails = set(unique_records) | set(unique_keys)

    def event_ids_for_processed_keys(self, processed_keys: list[str]) -> list[str]:
        """Return known calendar event IDs for processed keys."""
        event_ids = []
        for key in processed_keys:
            record = self.processed_records.get(key)
            if record and record.event_id:
                event_ids.append(record.event_id)
        return event_ids

    def get_label_id(self, label_name: str) -> str:
        """Get label ID"""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])
            for label in labels:
                if label["name"] == label_name:
                    return label["id"]
            raise ValueError(
                f"Label '{label_name}' does not exist. Please create it in Gmail first"
            )
        except HttpError as error:
            raise GmailError(f"Failed to get label: {error}") from error

    def get_emails_with_label(self, label_name: str) -> List[dict]:
        """Get emails with specific label within the last N days"""
        try:
            # Build date-based query
            if self.days_back > 0:
                since_date = (datetime.now() - timedelta(days=self.days_back)).strftime(
                    "%Y/%m/%d"
                )
                query = f"label:{label_name} after:{since_date}"
            else:
                query = f"label:{label_name}"

            logger.debug(f"Gmail query: {query}")

            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=10)
                .execute()
            )
            return results.get("messages", [])
        except HttpError as error:
            raise GmailError(f"Failed to get emails: {error}") from error

    def get_email_details(self, msg_id: str) -> MailParser:
        """Get email details and parse with mail-parser"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="raw")
                .execute()
            )
            raw_data = base64.urlsafe_b64decode(message["raw"])
            from email.parser import BytesParser

            email_message = BytesParser().parsebytes(raw_data)
            return MailParser(email_message)
        except HttpError as error:
            raise GmailError(f"Failed to get email details: {error}") from error

    def get_sender_email(self, mail: MailParser) -> str:
        """Extract sender email address"""
        from_header = mail.from_
        if from_header:
            if isinstance(from_header, list):
                return from_header[0][1] if from_header[0] else ""
            else:
                return from_header[1]
        return ""

    def get_email_subject(self, mail: MailParser) -> str:
        """Extract email subject"""
        subject = mail.subject
        if subject:
            if isinstance(subject, list):
                return str(subject[0]) if subject[0] else ""
            else:
                return str(subject).strip()
        return ""

    def get_pdf_attachments(
        self, mail: MailParser, msg_id: str, download_dir: Path
    ) -> List[Path]:
        """Download PDF attachments from email"""
        downloaded_files = []

        for attachment in mail.attachments:
            filename = attachment.get("filename", "")
            content_type = attachment.get("mail_content_type", "")

            # Check if this is a PDF
            is_pdf = (
                filename.lower().endswith(".pdf")
                or content_type == "application/pdf"
            )

            if not is_pdf:
                continue

            file_data = base64.b64decode(attachment.get("payload", ""))
            download_path = download_dir / f"{msg_id}_{filename}"

            with open(download_path, "wb") as f:
                f.write(file_data)

            downloaded_files.append(download_path)

        return downloaded_files

    def fetch_pending(self) -> List[BillEmail]:
        """
        Fetch emails with PDF attachments that haven't been processed.
        Returns list of BillEmail objects.
        """
        # Reload processed emails to catch any changes since init
        self._load_processed_emails()

        self.download_dir.mkdir(parents=True, exist_ok=True)

        emails: List[BillEmail] = []
        messages = self.get_emails_with_label(self.label)

        for msg in messages:
            msg_id = msg["id"]

            # Skip already processed
            if not self.ignore_processed and msg_id in self.processed_emails:
                logger.debug(f"Skipping already processed email: {msg_id}")
                continue

            mail = self.get_email_details(msg_id)
            sender_email = self.get_sender_email(mail)
            email_subject = self.get_email_subject(mail)
            pdf_files = self.get_pdf_attachments(mail, msg_id, self.download_dir)

            for pdf_path in pdf_files:
                email = BillEmail(
                    msg_id=msg_id,
                    sender=sender_email,
                    subject=email_subject,
                    pdf_path=pdf_path,
                )
                if (
                    not self.ignore_processed
                    and email.processed_key in self.processed_emails
                ):
                    logger.debug(
                        f"Skipping already processed attachment: {email.processed_key}"
                    )
                    continue

                emails.append(email)

        return emails
