"""Data models for bill-notify"""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional


@dataclass
class BillEmail:
    """Represents an email with bill PDF attachment"""

    msg_id: str
    sender: str
    subject: str
    pdf_path: Path

    def __post_init__(self):
        if isinstance(self.pdf_path, str):
            self.pdf_path = Path(self.pdf_path)


@dataclass
class ExtractedBill:
    """Bill data extracted from PDF via LLM"""

    due_date: date
    summary: str
    amount: Optional[str]
    source: BillEmail

    @property
    def is_expired(self) -> bool:
        """Check if the bill due date has passed"""
        return self.due_date < datetime.now().date()


@dataclass
class BillAnalysisResult:
    """Result of bill analysis by LLM"""

    status: Literal["success", "not_bill", "failed"]
    bill: Optional[ExtractedBill] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def should_retry(self) -> bool:
        """Failed results can be retried (technical error)"""
        return self.status == "failed"

    @property
    def should_skip(self) -> bool:
        """Should mark email as processed (not a bill or success)"""
        return self.status in ("success", "not_bill")


@dataclass
class ProcessingSummary:
    """Summary of processing run"""

    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    processed_emails: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.success_count + self.skipped_count + self.failed_count

    @property
    def has_failures(self) -> bool:
        return self.failed_count > 0


@dataclass
class CalendarEvent:
    """Represents a calendar event to be created"""

    summary: str
    due_date: date
    description: str
    reminder_days: int = 3

    def build_description(self, source: BillEmail) -> str:
        """Build event description with source info"""
        return f"Automatically created bill reminder\nSource: {source.pdf_path.name}\nEmail Subject: {source.subject}\nSender: {source.sender}"