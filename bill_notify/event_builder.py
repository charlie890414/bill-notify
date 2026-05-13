"""Calendar event construction helpers."""

from datetime import date, datetime

from bill_notify.constants import (
    EVENT_SUMMARY_PREFIX,
    EVENT_SUMMARY_SUFFIX,
    PREFIXES_TO_REMOVE,
)
from bill_notify.models import CalendarEvent, ExtractedBill


def build_calendar_event(
    bill: ExtractedBill,
    reminder_days: int | list[int],
    extracted_on: date | None = None,
) -> CalendarEvent:
    """Build a CalendarEvent from extracted bill data."""
    summary = bill.summary
    if not summary and bill.source:
        summary = _clean_subject(bill.source.subject)

    if not summary and bill.source:
        summary = bill.source.pdf_path.stem

    if not summary:
        summary = "Bill Payment"

    description_lines = ["Automatically created bill reminder"]
    if bill.source:
        description_lines.append(f"Source Key: {bill.source.processed_key}")
        description_lines.append(f"Source: {bill.source.pdf_path.name}")
        description_lines.append(f"Email Subject: {bill.source.subject}")
        description_lines.append(f"Sender: {bill.source.sender}")

    description_lines.append(f"Extracted: {extracted_on or datetime.now().date()}")

    if bill.amount:
        description_lines.append(f"Amount: {bill.amount}")

    return CalendarEvent(
        summary=f"{EVENT_SUMMARY_PREFIX} {summary} {EVENT_SUMMARY_SUFFIX}",
        due_date=bill.due_date,
        description="\n".join(description_lines),
        reminder_days=reminder_days if isinstance(reminder_days, list) else [reminder_days],
    )


def _clean_subject(subject: str) -> str:
    """Remove bill-related prefixes from subject."""
    cleaned = subject.strip()
    lower = cleaned.lower()

    for prefix in PREFIXES_TO_REMOVE:
        if lower.startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
            break

    return cleaned
