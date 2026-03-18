"""Gmail email fetcher module"""

import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from googleapiclient.errors import HttpError
from bill_notify.auth_manager import AuthManager
from bill_notify.config import AppConfig


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
            raise Exception(f"Failed to get label: {error}")

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
            raise Exception(f"Failed to get emails: {error}")

    def get_email_details(self, msg_id: str) -> dict:
        """Get email details"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            return message
        except HttpError as error:
            raise Exception(f"Failed to get email details: {error}")

    def get_sender_email(self, message: dict) -> str:
        """Extract sender email address from message headers"""
        headers = message.get("payload", {}).get("headers", [])
        for header in headers:
            if header.get("name", "").lower() == "from":
                from_header = header.get("value", "")
                # Extract email from format like: "Name <email@example.com>"
                if "<" in from_header and ">" in from_header:
                    start = from_header.find("<") + 1
                    end = from_header.find(">")
                    return from_header[start:end].strip()
                else:
                    return from_header.strip()
        return ""

    def get_email_subject(self, message: dict) -> str:
        """Extract email subject from message headers"""
        headers = message.get("payload", {}).get("headers", [])
        for header in headers:
            if header.get("name", "").lower() == "subject":
                return header.get("value", "").strip()
        return ""

    def get_pdf_attachments(self, message: dict, download_dir: Path) -> List[Path]:
        """Download PDF attachments from email"""
        downloaded_files = []
        msg_id = message["id"]

        if "payload" not in message or "parts" not in message["payload"]:
            return downloaded_files

        parts = message["payload"]["parts"]
        for part in parts:
            if part.get("filename", "").lower().endswith(".pdf"):
                attachment_id = part["body"]["attachmentId"]
                attachment = (
                    self.service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=msg_id, id=attachment_id)
                    .execute()
                )
                file_data = base64.urlsafe_b64decode(attachment["data"])
                filename = part["filename"]

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

            email_details = self.get_email_details(msg_id)
            sender_email = self.get_sender_email(email_details)
            email_subject = self.get_email_subject(email_details)
            pdf_files = self.get_pdf_attachments(email_details, download_dir)

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