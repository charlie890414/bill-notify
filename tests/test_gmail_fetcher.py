"""Tests for GmailFetcher processed record behavior."""

import json
from pathlib import Path

from bill_notify.gmail_fetcher import GmailFetcher
from bill_notify.models import BillEmail, ProcessedRecord


class FakeGmailProvider:
    def gmail_service(self):
        return None


class FakeFetcher(GmailFetcher):
    def __init__(self, processed_log, ignore_processed=False):
        super().__init__(
            gmail_service=FakeGmailProvider(),
            download_dir=Path("downloads"),
            processed_log=processed_log,
            ignore_processed=ignore_processed,
        )

    def get_emails_with_label(self, label_name):
        return [{"id": "msg-1"}]

    def get_email_details(self, msg_id):
        return object()

    def get_sender_email(self, mail):
        return "billing@example.com"

    def get_email_subject(self, mail):
        return "Bill"

    def get_pdf_attachments(self, mail, msg_id, download_dir):
        return [Path("msg-1_bill.pdf")]


def test_fetch_pending_skips_processed_attachment(tmp_path):
    processed_log = tmp_path / "processed.log"
    processed_log.write_text("msg-1:msg-1_bill.pdf\n", encoding="utf-8")
    fetcher = FakeFetcher(processed_log)

    assert fetcher.fetch_pending() == []


def test_fetch_pending_skips_processed_attachment_from_jsonl(tmp_path):
    processed_log = tmp_path / "processed.log"
    processed_log.write_text(
        json.dumps(
            {
                "key": "msg-1:msg-1_bill.pdf",
                "status": "success",
                "processed_at": "2026-05-14T00:00:00",
                "msg_id": "msg-1",
                "sender": "billing@example.com",
                "subject": "Bill",
                "pdf_path": "msg-1_bill.pdf",
                "event_id": "event-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fetcher = FakeFetcher(processed_log)

    assert fetcher.fetch_pending() == []
    assert fetcher.event_ids_for_processed_keys(["msg-1:msg-1_bill.pdf"]) == [
        "event-1"
    ]


def test_fetch_pending_ignores_processed_records_when_forced(tmp_path):
    processed_log = tmp_path / "processed.log"
    processed_log.write_text("msg-1:msg-1_bill.pdf\n", encoding="utf-8")
    fetcher = FakeFetcher(processed_log, ignore_processed=True)

    emails = fetcher.fetch_pending()

    assert emails == [
        BillEmail(
            msg_id="msg-1",
            sender="billing@example.com",
            subject="Bill",
            pdf_path=Path("msg-1_bill.pdf"),
        )
    ]


def test_replace_processed_overwrites_existing_log(tmp_path):
    processed_log = tmp_path / "processed.log"
    processed_log.write_text("old\n", encoding="utf-8")
    fetcher = FakeFetcher(processed_log)

    fetcher.replace_processed(["new-1", "new-1", "new-2"])

    assert processed_log.read_text(encoding="utf-8") == "new-1\nnew-2\n"
    assert fetcher.processed_emails == {"new-1", "new-2"}


def test_replace_processed_writes_jsonl_records(tmp_path):
    processed_log = tmp_path / "processed.log"
    fetcher = FakeFetcher(processed_log)
    record = ProcessedRecord(
        key="msg-1:bill.pdf",
        status="success",
        processed_at="2026-05-14T00:00:00",
        msg_id="msg-1",
        sender="billing@example.com",
        subject="Bill",
        pdf_path="bill.pdf",
        event_id="event-1",
    )

    fetcher.replace_processed([record])

    assert json.loads(processed_log.read_text(encoding="utf-8")) == {
        "key": "msg-1:bill.pdf",
        "status": "success",
        "processed_at": "2026-05-14T00:00:00",
        "msg_id": "msg-1",
        "sender": "billing@example.com",
        "subject": "Bill",
        "pdf_path": "bill.pdf",
        "event_id": "event-1",
        "error": None,
    }
    assert fetcher.processed_emails == {"msg-1:bill.pdf"}
    assert fetcher.event_ids_for_processed_keys(["msg-1:bill.pdf"]) == ["event-1"]
