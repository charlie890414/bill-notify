"""Google Calendar sync module"""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bill_notify.config import AppConfig


class CalendarSync:
    """Google Calendar synchronizer"""

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, config: AppConfig):
        self.config = config
        self.service = self._authenticate()

    def _authenticate(self) -> Any:
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

        return build("calendar", "v3", credentials=creds)

    def create_event(
        self,
        summary: str,
        due_date: date,
        description: str = "",
        reminder_days: int = 3,
    ) -> str:
        """
        Create event in calendar
        Args:
            summary: Event title
            due_date: Due date
            description: Event description
            reminder_days: Days in advance for reminder
        Returns:
            Created event ID
        """
        # Event start and end time (set as all-day event)
        start_date = due_date.isoformat()
        end_date = (due_date + timedelta(days=1)).isoformat()

        event = {
            "summary": summary,
            "description": description,
            "start": {
                "date": start_date,
                "timeZone": "Asia/Taipei",
            },
            "end": {
                "date": end_date,
                "timeZone": "Asia/Taipei",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60 * reminder_days},
                    {"method": "popup", "minutes": 24 * 60 * reminder_days},
                ],
            },
        }

        try:
            event_result = (
                self.service.events()
                .insert(calendarId=self.config.calendar.calendar_id, body=event)
                .execute()
            )
            print(f"Created calendar event: {summary} - {start_date}")
            return event_result["id"]
        except HttpError as error:
            raise Exception(f"Failed to create calendar event: {error}")

    def check_event_exists(self, due_date: date, summary_keywords: list[str]) -> bool:
        """
        Check if similar event exists on specified date
        Args:
            due_date: Date
            summary_keywords: List of summary keywords
        Returns:
            Whether event exists
        """
        try:
            time_min = datetime.combine(due_date, datetime.min.time()).isoformat() + "Z"
            time_max = datetime.combine(due_date, datetime.max.time()).isoformat() + "Z"

            events_result = (
                self.service.events()
                .list(
                    calendarId=self.config.calendar.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            for event in events:
                summary = event.get("summary", "").lower()
                for keyword in summary_keywords:
                    if keyword.lower() in summary:
                        return True

            return False
        except HttpError as error:
            raise Exception(f"Failed to check event: {error}")