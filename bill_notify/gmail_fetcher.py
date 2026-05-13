"""Gmail email fetcher module"""

import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from googleapiclient.errors import HttpError
from mailparser import MailParser
from bill_notify.models import BillEmail
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
    ):
        self._gmail = gmail_service
        self.download_dir = Path(download_dir)
        self.processed_log = Path(processed_log)
        self.label = label
        self.days_back = days_back
        self._load_processed_emails()

    @property
    def service(self):
        """Get the Gmail service"""
        return self._gmail.gmail_service()

    def _load_processed_emails(self):
        """Load processed email IDs from log file"""
        self.processed_emails: set[str] = set()
        if self.processed_log.exists():
            with open(self.processed_log, "r", encoding="utf-8") as f:
                self.processed_emails = set(line.strip() for line in f if line.strip())

    def _reload_processed_emails(self):
        """Reload processed emails from log file (for use after marking)"""
        self._load_processed_emails()

    def mark_processed(self, msg_id: str):
        """Mark email as processed"""
        with open(self.processed_log, "a", encoding="utf-8") as f:
            f.write(f"{msg_id}\n")
        self.processed_emails.add(msg_id)

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
            if msg_id in self.processed_emails:
                logger.debug(f"Skipping already processed email: {msg_id}")
                continue

            mail = self.get_email_details(msg_id)
            sender_email = self.get_sender_email(mail)
            email_subject = self.get_email_subject(mail)
            pdf_files = self.get_pdf_attachments(mail, msg_id, self.download_dir)

            for pdf_path in pdf_files:
                emails.append(
                    BillEmail(
                        msg_id=msg_id,
                        sender=sender_email,
                        subject=email_subject,
                        pdf_path=pdf_path,
                    )
                )

        return emails