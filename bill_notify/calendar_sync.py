"""Google Calendar sync module"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from googleapiclient.errors import HttpError
from bill_notify.auth_manager import AuthManager
from bill_notify.config import AppConfig


logger = logging.getLogger(__name__)


class CalendarSync:
    """Google Calendar synchronizer"""

    def __init__(self, config: AppConfig):
        self.config = config
        auth_manager = AuthManager(
            credentials_file=config.gmail.credentials_file,
            token_file=config.gmail.token_file
        )
        self.service = auth_manager.build_service("calendar", "v3")

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
            logger.info(f"Created calendar event: {summary} - {start_date}")
            return event_result["id"]
        except HttpError as error:
            raise Exception(f"Failed to create calendar event: {error}")

    def check_event_exists(
        self,
        due_date: date,
        summary_keywords: list[str],
        sender_email: Optional[str] = None,
        pdf_filename: Optional[str] = None,
    ) -> bool:
        """
        Check if similar event exists on specified date
        Args:
            due_date: Date
            summary_keywords: List of summary keywords
            sender_email: Sender email to check for duplicates (if provided, checks description)
            pdf_filename: PDF filename to check for duplicates (if provided, checks description)
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
                # First check by summary keywords (broad match)
                summary = event.get("summary", "").lower()
                matches_keywords = any(
                    keyword.lower() in summary for keyword in summary_keywords
                )
                
                if not matches_keywords:
                    continue
                
                # If sender or pdf filename provided, check description for source to avoid duplicates from different senders
                if sender_email or pdf_filename:
                    description = event.get("description", "").lower()
                    
                    # Check if this event is from the same sender
                    if sender_email and sender_email.lower() in description:
                        return True
                    
                    # Check if this event is from the same PDF file
                    if pdf_filename and pdf_filename.lower() in description:
                        return True
                    
                    # If we have sender/pdf info but neither matches, continue checking other events
                    continue
                else:
                    # No source info provided, use broad keyword match
                    return True

            return False
        except HttpError as error:
            raise Exception(f"Failed to check event: {error}")