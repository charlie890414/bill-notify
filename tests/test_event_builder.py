"""Tests for calendar event construction."""

from datetime import date
from pathlib import Path

from bill_notify.event_builder import build_calendar_event
from bill_notify.models import BillEmail, ExtractedBill


def test_build_calendar_event_uses_source_metadata_and_reminder_days():
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="",
        amount="NT$ 500",
        source=BillEmail(
            msg_id="msg-1",
            sender="billing@example.com",
            subject="Bill: Internet",
            pdf_path=Path("internet.pdf"),
        ),
    )

    event = build_calendar_event(
        bill,
        reminder_days=5,
        extracted_on=date(2026, 5, 14),
    )

    assert event.summary == "[Bill] Internet - Payment Due"
    assert event.reminder_days == [5]
    assert "Source: internet.pdf" in event.description
    assert "Sender: billing@example.com" in event.description
    assert "Amount: NT$ 500" in event.description


def test_build_calendar_event_handles_bill_without_source():
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="Card Payment",
        amount=None,
    )

    event = build_calendar_event(bill, reminder_days=2)

    assert event.summary == "[Bill] Card Payment - Payment Due"
    assert event.reminder_days == [2]


def test_build_calendar_event_accepts_multiple_reminder_days():
    bill = ExtractedBill(
        due_date=date(2026, 6, 1),
        summary="Card Payment",
        amount=None,
    )

    event = build_calendar_event(bill, reminder_days=[7, 3, 1])

    assert event.reminder_days == [7, 3, 1]
