"""Tests for Google Calendar event payload construction."""

from datetime import date
from pathlib import Path

from bill_notify.calendar_sync import CalendarSync
from bill_notify.models import BillEmail, CalendarEvent, ExtractedBill


class FakeExecute:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class FakeInsert:
    def __init__(self):
        self.calls = []

    def insert(self, **kwargs):
        self.calls.append(kwargs)
        return FakeExecute({"id": "event-1"})


class FakeEvents:
    def __init__(self, events=None):
        self.insert_api = FakeInsert()
        self.events = list(events or [])
        self.list_calls = []
        self.delete_calls = []

    def insert(self, **kwargs):
        return self.insert_api.insert(**kwargs)

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return FakeExecute({"items": self.events})

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)
        return FakeExecute({})


class FakeCalendarService:
    def __init__(self, events=None):
        self.events_api = FakeEvents(events)

    def events(self):
        return self.events_api


class FakeCalendarProvider:
    def __init__(self, events=None):
        self.service = FakeCalendarService(events)

    def calendar_service(self):
        return self.service


def test_create_event_expands_multiple_reminder_days():
    provider = FakeCalendarProvider()
    calendar = CalendarSync(provider, calendar_id="primary")
    event = CalendarEvent(
        summary="Bill",
        due_date=date(2026, 6, 1),
        description="Description",
        reminder_days=[7, 3, 1],
    )

    event_id = calendar.create_event(event)

    assert event_id == "event-1"
    body = provider.service.events_api.insert_api.calls[0]["body"]
    assert body["reminders"]["overrides"] == [
        {"method": "popup", "minutes": 7 * 24 * 60},
        {"method": "popup", "minutes": 3 * 24 * 60},
        {"method": "popup", "minutes": 1 * 24 * 60},
        {"method": "email", "minutes": 7 * 24 * 60},
        {"method": "email", "minutes": 3 * 24 * 60},
    ]


def test_create_event_limits_reminder_overrides_to_google_calendar_maximum():
    provider = FakeCalendarProvider()
    calendar = CalendarSync(provider, calendar_id="primary")
    event = CalendarEvent(
        summary="Bill",
        due_date=date(2026, 6, 1),
        description="Description",
        reminder_days=[10, 7, 5, 3, 1, 0],
    )

    calendar.create_event(event)

    body = provider.service.events_api.insert_api.calls[0]["body"]
    assert body["reminders"]["overrides"] == [
        {"method": "popup", "minutes": 10 * 24 * 60},
        {"method": "popup", "minutes": 7 * 24 * 60},
        {"method": "popup", "minutes": 5 * 24 * 60},
        {"method": "popup", "minutes": 3 * 24 * 60},
        {"method": "popup", "minutes": 1 * 24 * 60},
    ]


def test_check_event_exists_returns_true_for_matching_event():
    provider = FakeCalendarProvider(
        events=[
            {
                "id": "old-event",
                "summary": "[Bill] Electricity - Payment Due",
                "description": "Source: bill.pdf\nSender: billing@example.com",
            }
        ]
    )
    calendar = CalendarSync(provider)
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="Electricity",
        amount=None,
        source=BillEmail(
            msg_id="msg-1",
            sender="billing@example.com",
            subject="Bill",
            pdf_path=Path("bill.pdf"),
        ),
    )

    assert calendar.check_event_exists(bill) is True
    assert provider.service.events_api.delete_calls == []


def test_check_event_exists_does_not_match_same_sender_with_different_source():
    provider = FakeCalendarProvider(
        events=[
            {
                "id": "old-event",
                "summary": "[Bill] HSBC Card - Payment Due",
                "description": (
                    "Source Key: old-msg:old_statement.pdf\n"
                    "Source: old_statement.pdf\n"
                    "Sender: cards@estatements.hsbc.com.tw"
                ),
            }
        ]
    )
    calendar = CalendarSync(provider)
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="HSBC Another Card",
        amount=None,
        source=BillEmail(
            msg_id="new-msg",
            sender="cards@estatements.hsbc.com.tw",
            subject="HSBC Bill",
            pdf_path=Path("new_statement.pdf"),
        ),
    )

    assert calendar.check_event_exists(bill) is False


def test_check_event_exists_matches_source_key():
    provider = FakeCalendarProvider(
        events=[
            {
                "id": "old-event",
                "summary": "[Bill] HSBC Card - Payment Due",
                "description": (
                    "Source Key: msg-1:statement.pdf\n"
                    "Source: different_name.pdf\n"
                    "Sender: cards@estatements.hsbc.com.tw"
                ),
            }
        ]
    )
    calendar = CalendarSync(provider)
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="HSBC Card",
        amount=None,
        source=BillEmail(
            msg_id="msg-1",
            sender="cards@estatements.hsbc.com.tw",
            subject="HSBC Bill",
            pdf_path=Path("statement.pdf"),
        ),
    )

    assert calendar.check_event_exists(bill) is True


def test_check_event_exists_deletes_matching_event_when_overwriting():
    provider = FakeCalendarProvider(
        events=[
            {
                "id": "old-event",
                "summary": "[Bill] Electricity - Payment Due",
                "description": "Source: bill.pdf\nSender: billing@example.com",
            }
        ]
    )
    calendar = CalendarSync(provider, overwrite_existing=True)
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="Electricity",
        amount=None,
        source=BillEmail(
            msg_id="msg-1",
            sender="billing@example.com",
            subject="Bill",
            pdf_path=Path("bill.pdf"),
        ),
    )

    assert calendar.check_event_exists(bill) is False
    assert provider.service.events_api.delete_calls == [
        {"calendarId": "primary", "eventId": "old-event"}
    ]
