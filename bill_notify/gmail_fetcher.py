"""Gmail email fetcher module"""
import base64
import json
import os
from pathlib import Path
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bill_notify.config import AppConfig


class GmailFetcher:
    """Gmail email fetcher"""

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ]

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

    def _authenticate(self) -> any:
        """OAuth 2.0 authentication"""
        creds = None
        token_path = Path(self.config.gmail.token_file)
        creds_path = Path(self.config.gmail.credentials_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_info(
                json.load(open(token_path)), self.SCOPES
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
                    str(creds_path), self.SCOPES
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
            raise ValueError(f"Label '{label_name}' does not exist. Please create it in Gmail first")
        except HttpError as error:
            raise Exception(f"Failed to get label: {error}")

    def get_unread_emails_with_label(self, label_name: str) -> List[dict]:
        """Get unread emails with specific label"""
        try:
            label_id = self.get_label_id(label_name)
            query = f"label:{label_id} is:unread"
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=50)
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

    def mark_as_read(self, msg_id: str):
        """Mark email as read"""
        try:
            self.service.users().messages().modify(
                userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except HttpError as error:
            raise Exception(f"Failed to mark email as read: {error}")

    def process_emails(self, download_dir: Optional[Path] = None) -> List[Path]:
        """
        Process unread emails, download PDF attachments
        Returns list of downloaded file paths
        """
        if download_dir is None:
            download_dir = Path(self.config.download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        unprocessed_files = []
        messages = self.get_unread_emails_with_label(self.config.gmail.gmail_label)

        for msg in messages:
            msg_id = msg["id"]
            if msg_id in self.processed_emails:
                continue

            email_details = self.get_email_details(msg_id)
            pdf_files = self.get_pdf_attachments(email_details, download_dir)

            if pdf_files:
                unprocessed_files.extend(pdf_files)
                self._save_processed_email(msg_id)
                self.mark_as_read(msg_id)
            else:
                # Mark as processed even without PDF attachment
                self._save_processed_email(msg_id)
                self.mark_as_read(msg_id)

        return unprocessed_files
