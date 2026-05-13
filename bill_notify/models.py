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

    @property
    def processed_key(self) -> str:
        """Unique key for this email attachment in the processed log."""
        return f"{self.msg_id}:{self.pdf_path.name}"


@dataclass
class ExtractedBill:
    """Bill data extracted from PDF via LLM"""

    due_date: date
    summary: str
    amount: Optional[str]
    source: Optional[BillEmail] = None

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
    event_id: Optional[str] = None

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
    processed_records: list["ProcessedRecord"] = field(default_factory=list)

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
    reminder_days: list[int] = field(default_factory=lambda: [3])

    def build_description(self, source: BillEmail) -> str:
        """Build event description with source info"""
        return f"Automatically created bill reminder\nSource: {source.pdf_path.name}\nEmail Subject: {source.subject}\nSender: {source.sender}"


@dataclass
class ProcessedRecord:
    """Structured processed attachment record."""

    key: str
    status: Literal["success", "not_bill"]
    processed_at: str
    msg_id: str
    sender: str
    subject: str
    pdf_path: str
    event_id: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def from_email_result(
        cls, email: BillEmail, result: BillAnalysisResult
    ) -> "ProcessedRecord":
        return cls(
            key=email.processed_key,
            status=result.status,  # type: ignore[arg-type]
            processed_at=datetime.now().isoformat(timespec="seconds"),
            msg_id=email.msg_id,
            sender=email.sender,
            subject=email.subject,
            pdf_path=str(email.pdf_path),
            event_id=result.event_id,
            error=result.error,
        )
