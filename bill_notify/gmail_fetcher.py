"""Gmail email fetcher module"""

import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from googleapiclient.errors import HttpError
from mailparser import MailParser
from bill_notify.auth_manager import AuthManager
from bill_notify.config import AppConfig
from bill_notify.exceptions import GmailError


logger = logging.getLogger(__name__)


class GmailFetcher:
    """Gmail email fetcher"""

    def __init__(self, config: AppConfig):
        self.config = config
        auth_manager = AuthManager(
            credentials_file=config.gmail.credentials_file,
            token_file=config.gmail.token_file
        )
        self.service = auth_manager.build_service("gmail", "v1")
        self.processed_log = Path(config.processed_log)
        self.processed_log.parent.mkdir(parents=True, exist_ok=True)
        self._load_processed_emails()

    def _load_processed_emails(self):
        """Load processed email IDs"""
        if self.processed_log.exists():
            with open(self.processed_log, "r", encoding="utf-8") as f:
                self.processed_emails = set(line.strip() for line in f if line.strip())
        else:
            self.processed_emails = set()

    def _save_processed_email(self, msg_id: str):
        """Save processed email ID"""
        with open(self.processed_log, "a", encoding="utf-8") as f:
            f.write(f"{msg_id}\n")
        self.processed_emails.add(msg_id)

    def _save_all_processed(self):
        """Save all processed email IDs to log"""
        with open(self.processed_log, "w", encoding="utf-8") as f:
            for msg_id in sorted(self.processed_emails):
                f.write(f"{msg_id}\n")

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
        """Get unread emails with specific label within the last N days"""
        try:
            # Build date-based query
            days_back = self.config.gmail.days_back
            if days_back > 0:
                since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
                query = f"label:{label_name} after:{since_date}"
            else:
                query = f"label:{label_name}"
            
            if self.config.verbose:
                logger.info(f"Gmail query: {query}")
            
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=10)
                .execute()
            )
            messages = results.get("messages", [])
            return messages
        except HttpError as error:
            raise GmailError(f"Failed to get emails: {error}") from error

    def get_email_details(self, msg_id: str) -> MailParser:
        """Get email details in raw format and parse with mail-parser"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="raw")
                .execute()
            )
            # Decode raw message data            
            raw_data = base64.urlsafe_b64decode(message["raw"])
            # Parse with mail-parser - needs email message object
            from email.parser import BytesParser
            email_message = BytesParser().parsebytes(raw_data)
            mail = MailParser(email_message)
            return mail
        except HttpError as error:
            raise GmailError(f"Failed to get email details: {error}") from error

    def get_sender_email(self, mail: MailParser) -> str:
        """Extract sender email address from parsed mail"""
        from_header = mail.from_
        if from_header:
            # from_str format: (name, email)
            # mail-parser may return a list or string
            if isinstance(from_header, list):
                # Take first sender if multiple
                return from_header[0][1] if from_header[0] else ""
            else:
                return from_header[1]
        return ""

    def get_email_subject(self, mail: MailParser) -> str:
        """Extract email subject from parsed mail"""
        subject = mail.subject
        if subject:
            # mail-parser may return a list or string
            if isinstance(subject, list):
                subject_str = str(subject[0]) if subject[0] else ""
            else:
                subject_str = str(subject)
            return subject_str.strip()
        return ""

    def get_pdf_attachments(self, mail, msg_id: str, download_dir: Path):
        downloaded_files = []

        for i, attachment in enumerate(mail.attachments):
            filename = attachment.get("filename")
            content_type = attachment.get("mail_content_type", "")
            if not (filename.endswith(".pdf") or "application/pdf" == content_type):
                continue
            file_data = base64.b64decode(attachment.get("payload"))

            is_pdf = (
                (filename and filename.lower().endswith(".pdf"))
                or content_type == "application/pdf"
            )

            if not is_pdf:
                continue

            download_path = download_dir / f"{msg_id}_{filename}"

            with open(download_path, "wb") as f:
                f.write(file_data)

            downloaded_files.append(download_path)

        return downloaded_files

    def process_emails(
        self, download_dir: Optional[Path] = None
    ) -> List[Tuple[str, Path, str, str]]:
        """
        Process unread emails, download PDF attachments
        Returns list of tuples: (msg_id, pdf_path, sender_email, email_subject)
        Note: This method now only fetches emails; marking as processed is done separately
        """
        if download_dir is None:
            download_dir = Path(self.config.download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        unprocessed_files = []
        messages = self.get_emails_with_label(self.config.gmail.gmail_label)

        for msg in messages:
            msg_id = msg["id"]
            # Skip already processed emails
            if msg_id in self.processed_emails:
                if self.config.verbose:
                    logger.debug(f"Skipping already processed email: {msg_id}")
                continue

            mail = self.get_email_details(msg_id)
            sender_email = self.get_sender_email(mail)
            email_subject = self.get_email_subject(mail)
            pdf_files = self.get_pdf_attachments(mail, msg_id, download_dir)

            if pdf_files:
                # Attach sender email and subject to each PDF file
                for pdf_path in pdf_files:
                    unprocessed_files.append((msg_id, pdf_path, sender_email, email_subject))
            # Note: We do NOT mark as processed here anymore - that's done after successful event creation

        return unprocessed_files

    def mark_processed(self, msg_id: str):
        """Mark a specific email as processed (to be called after successful event creation)"""
        self._save_processed_email(msg_id)

    def get_processed_count(self) -> int:
        """Get count of processed emails"""
        return len(self.processed_emails)