"""Gmail email fetcher module"""

import base64
import json
from pathlib import Path
from typing import Any, List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bill_notify.config import AppConfig, SCOPES


class GmailFetcher:
    """Gmail email fetcher"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.service = self._authenticate()
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

    def _authenticate(self) -> Any:
        """OAuth 2.0 authentication"""
        creds = None
        token_path = Path(self.config.gmail.token_file)
        creds_path = Path(self.config.gmail.credentials_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_info(
                json.load(open(token_path)), SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not creds_path.exists():
                    raise FileNotFoundError(
                        f"Please create OAuth 2.0 client credentials in Google Cloud Console and save to {creds_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as token:
                token.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

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
        """Get unread emails with specific label"""
        try:
            query = f"label:{label_name}"
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
    ) -> List[tuple[Path, str, str]]:
        """
        Process unread emails, download PDF attachments
        Returns list of tuples: (pdf_path, sender_email, email_subject)
        """
        if download_dir is None:
            download_dir = Path(self.config.download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        unprocessed_files = []
        messages = self.get_emails_with_label(self.config.gmail.gmail_label)

        for msg in messages:
            msg_id = msg["id"]
            if msg_id in self.processed_emails:
                continue

            email_details = self.get_email_details(msg_id)
            sender_email = self.get_sender_email(email_details)
            email_subject = self.get_email_subject(email_details)
            pdf_files = self.get_pdf_attachments(email_details, download_dir)

            if pdf_files:
                # Attach sender email and subject to each PDF file
                for pdf_path in pdf_files:
                    unprocessed_files.append((pdf_path, sender_email, email_subject))
            self._save_processed_email(msg_id)

        return unprocessed_files
