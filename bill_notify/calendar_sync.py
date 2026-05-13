"""Google Calendar sync module"""

import logging
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
from bill_notify.interfaces import CalendarServiceProvider
from bill_notify.models import ExtractedBill, CalendarEvent
from bill_notify.constants import DEFAULT_TIMEZONE, DEFAULT_SUMMARY_KEYWORDS
from bill_notify.event_builder import build_calendar_event
from bill_notify.exceptions import CalendarError


logger = logging.getLogger(__name__)

MAX_EVENT_REMINDERS = 5


class CalendarSync:
    """Google Calendar synchronizer"""

    def __init__(
        self,
        calendar_service: CalendarServiceProvider,
        calendar_id: str = "primary",
        reminder_days: int | list[int] = 3,
        timezone: str = DEFAULT_TIMEZONE,
        overwrite_existing: bool = False,
    ):
        self._calendar = calendar_service
        self.calendar_id = calendar_id
        self.reminder_days = reminder_days
        self.timezone = timezone
        self.overwrite_existing = overwrite_existing

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

        logger.debug("Calendar event summary: %s", event.summary)

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
                "overrides": self._build_reminder_overrides(event.reminder_days),
            },
        }

        logger.debug("Calendar event body: %s", event_body)

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

    def create_event_from_bill(
        self, bill: ExtractedBill, reminder_days: int | list[int] = 3
    ) -> str:
        """
        Create calendar event from extracted bill.
        Convenience method that builds the event automatically.
        """
        event = build_calendar_event(bill, reminder_days)
        return self.create_event(event)

    def _build_reminder_overrides(self, reminder_days: list[int]) -> list[dict]:
        """Build Calendar reminder overrides within Google's per-event limit."""
        overrides = [
            {"method": "popup", "minutes": 24 * 60 * reminder_day}
            for reminder_day in reminder_days
        ]
        overrides.extend(
            {"method": "email", "minutes": 24 * 60 * reminder_day}
            for reminder_day in reminder_days
        )

        if len(overrides) > MAX_EVENT_REMINDERS:
            logger.warning(
                "Calendar supports at most %s reminders per event; "
                "truncating %s requested reminders",
                MAX_EVENT_REMINDERS,
                len(overrides),
            )

        return overrides[:MAX_EVENT_REMINDERS]

    def check_event_exists(self, bill: ExtractedBill) -> bool:
        """
        Check if similar event exists for this bill.
        Prevents duplicate events from same sender/file.
        """
        try:
            matching_events = self._find_matching_events(bill)
            if not matching_events:
                return False

            if self.overwrite_existing:
                for event in matching_events:
                    event_id = event.get("id")
                    if event_id:
                        self.delete_event(event_id)
                return False

            return True
        except HttpError as error:
            raise CalendarError(f"Failed to check event: {error}") from error

    def delete_event(self, event_id: str) -> None:
        """Delete an event from calendar."""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()
            logger.info(f"Deleted calendar event: {event_id}")
        except HttpError as error:
            raise CalendarError(f"Failed to delete calendar event: {error}") from error

    def _find_matching_events(self, bill: ExtractedBill) -> list[dict]:
        """Find events matching the bill source on the bill due date."""
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
        return [event for event in events if self._event_matches_bill(event, bill)]

    def _event_matches_bill(self, event: dict, bill: ExtractedBill) -> bool:
        """Check whether an existing event matches the bill."""
        summary = event.get("summary", "").lower()
        matches_keywords = any(
            keyword.lower() in summary for keyword in DEFAULT_SUMMARY_KEYWORDS
        )

        if not matches_keywords:
            return False

        if bill.source:
            description = event.get("description", "").lower()

            source_key = bill.source.processed_key.lower()
            if source_key and source_key in description:
                return True

            pdf_name = bill.source.pdf_path.name.lower()
            if (
                bill.source.pdf_path
                and pdf_name
                and pdf_name in description
            ):
                return True

            if not pdf_name and bill.source.sender:
                return bill.source.sender.lower() in description

            return False

        return True
