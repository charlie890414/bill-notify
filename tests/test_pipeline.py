"""Pipeline unit tests with fake services."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from bill_notify.models import BillAnalysisResult, BillEmail, ExtractedBill
from bill_notify.pipeline import BillPipeline


class FakeGmail:
    def __init__(self, emails):
        self._emails = emails
        self.marked = []
        self.replaced = None
        self.event_ids = []

    def fetch_pending(self):
        return list(self._emails)

    def mark_processed(self, processed_key: str):
        self.marked.append(processed_key)

    def mark_processed_record(self, record):
        self.marked.append(record)

    def replace_processed(self, processed_records):
        self.replaced = list(processed_records)

    def event_ids_for_processed_keys(self, processed_keys: list[str]):
        return list(self.event_ids)


class FakePDFProcessor:
    def __init__(self, failures=None):
        self.failures = set(failures or [])

    @property
    def ocr(self):
        return object()

    def process_pdf(self, pdf_path, sender_email=""):
        if Path(pdf_path).name in self.failures:
            raise RuntimeError("PDF failed")
        return f"text for {Path(pdf_path).name}"


class FakeLLMAnalyzer:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def analyze_pdf(self, pdf_context, email_subject="", sender_email=""):
        self.calls.append((pdf_context, email_subject, sender_email))
        return self._results.pop(0)


class FakeCalendar:
    def __init__(self, duplicate=False, reminder_days=3):
        self.duplicate = duplicate
        self.reminder_days = reminder_days
        self.created = []
        self.deleted = []

    def check_event_exists(self, bill):
        return self.duplicate

    def create_event(self, event):
        self.created.append(event)
        return "event-1"

    def delete_event(self, event_id):
        self.deleted.append(event_id)


def make_email(msg_id="msg-1", filename="bill.pdf"):
    return BillEmail(
        msg_id=msg_id,
        sender="billing@example.com",
        subject="Electricity Bill",
        pdf_path=Path(filename),
    )


def make_bill(summary="Electricity", amount="$42"):
    return ExtractedBill(
        due_date=date.today() + timedelta(days=7),
        summary=summary,
        amount=amount,
    )


def make_pipeline(
    emails, llm_results, calendar=None, pdf_processor=None, force_reprocess=False
):
    gmail = FakeGmail(emails)
    pipeline = BillPipeline(
        gmail=gmail,
        pdf_processor=pdf_processor or FakePDFProcessor(),
        llm_analyzer=FakeLLMAnalyzer(llm_results),
        calendar=calendar or FakeCalendar(reminder_days=9),
        processed_log=Path("processed.log"),
        reminder_days=[9, 3],
        force_reprocess=force_reprocess,
    )
    return pipeline, gmail


@pytest.mark.asyncio
async def test_success_creates_event_with_source_and_reminder_days():
    email = make_email()
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="success", bill=make_bill())],
    )

    summary = await pipeline.run()

    assert summary.success_count == 1
    assert [record.key for record in gmail.marked] == ["msg-1:bill.pdf"]
    assert [record.event_id for record in gmail.marked] == ["event-1"]
    assert len(pipeline.calendar.created) == 1

    event = pipeline.calendar.created[0]
    assert event.reminder_days == [9, 3]
    assert "Source: bill.pdf" in event.description
    assert "Sender: billing@example.com" in event.description


@pytest.mark.asyncio
async def test_not_bill_marks_attachment_processed():
    email = make_email()
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="not_bill")],
    )

    summary = await pipeline.run()

    assert summary.skipped_count == 1
    assert [record.key for record in gmail.marked] == ["msg-1:bill.pdf"]
    assert [record.event_id for record in gmail.marked] == [None]
    assert pipeline.calendar.created == []


@pytest.mark.asyncio
async def test_failed_analysis_does_not_mark_processed():
    email = make_email()
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="failed", error="LLM failed")],
    )

    summary = await pipeline.run()

    assert summary.failed_count == 1
    assert gmail.marked == []
    assert pipeline.calendar.created == []


@pytest.mark.asyncio
async def test_duplicate_event_skips_creation_but_marks_processed():
    email = make_email()
    calendar = FakeCalendar(duplicate=True, reminder_days=9)
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="success", bill=make_bill())],
        calendar=calendar,
    )

    summary = await pipeline.run()

    assert summary.skipped_count == 1
    assert [record.key for record in gmail.marked] == ["msg-1:bill.pdf"]
    assert calendar.created == []


@pytest.mark.asyncio
async def test_multi_attachment_partial_failure_marks_only_finished_attachment():
    first = make_email(msg_id="msg-1", filename="first.pdf")
    second = make_email(msg_id="msg-1", filename="second.pdf")
    pipeline, gmail = make_pipeline(
        [first, second],
        [BillAnalysisResult(status="success", bill=make_bill())],
        pdf_processor=FakePDFProcessor(failures={"second.pdf"}),
    )

    summary = await pipeline.run()

    assert summary.success_count == 1
    assert summary.failed_count == 1
    assert [record.key for record in gmail.marked] == ["msg-1:first.pdf"]


@pytest.mark.asyncio
async def test_force_reprocess_overwrites_processed_records_instead_of_appending():
    email = make_email()
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="success", bill=make_bill())],
        force_reprocess=True,
    )

    summary = await pipeline.run()

    assert summary.success_count == 1
    assert gmail.marked == []
    assert [record.key for record in gmail.replaced] == ["msg-1:bill.pdf"]
    assert [record.event_id for record in gmail.replaced] == ["event-1"]


@pytest.mark.asyncio
async def test_force_reprocess_deletes_previous_event_ids_before_processing():
    email = make_email()
    calendar = FakeCalendar()
    pipeline, gmail = make_pipeline(
        [email],
        [BillAnalysisResult(status="success", bill=make_bill())],
        calendar=calendar,
        force_reprocess=True,
    )
    gmail.event_ids = ["old-event-1"]

    await pipeline.run()

    assert calendar.deleted == ["old-event-1"]
