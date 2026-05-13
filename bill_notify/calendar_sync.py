"""Google Calendar sync module"""

import logging
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
from bill_notify.interfaces import CalendarServiceProvider
from bill_notify.models import ExtractedBill, CalendarEvent
from bill_notify.constants import DEFAULT_TIMEZONE, DEFAULT_SUMMARY_KEYWORDS
from bill_notify.exceptions import CalendarError


logger = logging.getLogger(__name__)


class CalendarSync:
    """Google Calendar synchronizer"""

    def __init__(
        self,
        calendar_service: CalendarServiceProvider,
        calendar_id: str = "primary",
        reminder_days: int = 3,
        timezone: str = DEFAULT_TIMEZONE,
    ):
        self._calendar = calendar_service
        self.calendar_id = calendar_id
        self.reminder_days = reminder_days
        self.timezone = timezone

    @property
    def service(self):
        """Get the Calendar service"""
        return self._calendar.calendar_service()

    def create_event(self, event: CalendarEvent) -> str:
        """
        Create an event in calendar.
        Args:
            event: CalendarEvent to create
        Returns:
            Created event ID
        """
        start_date = event.due_date.isoformat()
        end_date = (event.due_date + timedelta(days=1)).isoformat()

        event_body = {
            "summary": event.summary,
            "description": event.description,
            "start": {
                "date": start_date,
                "timeZone": self.timezone,
            },
            "end": {
                "date": end_date,
                "timeZone": self.timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60 * event.reminder_days},
                    {"method": "popup", "minutes": 24 * 60 * event.reminder_days},
                ],
            },
        }

        try:
            result = (
                self.service.events()
                .insert(calendarId=self.calendar_id, body=event_body)
                .execute()
            )
            event_id = result["id"]
            logger.info(f"Created calendar event: {event.summary} - {start_date}")
            return event_id
        except HttpError as error:
            raise CalendarError(f"Failed to create calendar event: {error}") from error

    def create_event_from_bill(self, bill: ExtractedBill, reminder_days: int = 3) -> str:
        """
        Create calendar event from extracted bill.
        Convenience method that builds the event automatically.
        """
        event = CalendarEvent(
            summary=f"[Bill] {bill.summary} - Payment Due",
            due_date=bill.due_date,
            description=bill.build_description(),
            reminder_days=reminder_days,
        )
        return self.create_event(event)

    def check_event_exists(self, bill: ExtractedBill) -> bool:
        """
        Check if similar event exists for this bill.
        Prevents duplicate events from same sender/file.
        """
        try:
            due_date = bill.due_date
            time_min = datetime.combine(due_date, datetime.min.time()).isoformat() + "Z"
            time_max = datetime.combine(due_date, datetime.max.time()).isoformat() + "Z"

            events_result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            for event in events:
                # Check summary keywords
                summary = event.get("summary", "").lower()
                matches_keywords = any(
                    keyword.lower() in summary for keyword in DEFAULT_SUMMARY_KEYWORDS
                )

                if not matches_keywords:
                    continue

                # Check description for source info (sender/file)
                if bill.source.sender or bill.source.pdf_path.name:
                    description = event.get("description", "").lower()

                    if bill.source.sender and bill.source.sender.lower() in description:
                        return True

                    if bill.source.pdf_path and bill.source.pdf_path.name.lower() in description:
                        return True

                    continue
                else:
                    return True

            return False
        except HttpError as error:
            raise CalendarError(f"Failed to check event: {error}") from error