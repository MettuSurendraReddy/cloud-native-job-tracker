import pytest

from job_tracker.config import Settings
from job_tracker.models import ApplicationDetails, ApplicationStatus, JobEmailExtraction
from job_tracker.worker.ingestion import (
    GmailPubSubIngestionWorker,
    HistoryCursorStore,
    build_ingestion_worker,
)


class FakeGmail:
    def __init__(self):
        self.list_calls = []
        self.messages = {
            "message-a": {"id": "message-a"},
            "message-b": {"id": "message-b"},
        }

    def get_profile(self):
        return {"emailAddress": "jobs@example.com"}

    def start_watch(self, topic_name):
        assert topic_name == "projects/demo/topics/gmail"
        return {"historyId": "100"}

    def list_message_ids_after(self, history_id):
        self.list_calls.append(history_id)
        return ["message-a", "message-b"], "105"

    def get_message(self, message_id):
        return self.messages[message_id]


class FakePubSubMessage:
    def __init__(self, data):
        self.data = data
        self.acked = False

    def ack(self):
        self.acked = True


def notification(history_id="105", email="jobs@example.com"):
    return FakePubSubMessage(f'{{"emailAddress":"{email}","historyId":"{history_id}"}}'.encode())


def test_worker_dispatches_messages_then_advances_cursor_and_acks(tmp_path):
    gmail = FakeGmail()
    cursor_store = HistoryCursorStore(tmp_path / "state.sqlite3")
    processed = []
    worker = GmailPubSubIngestionWorker(
        gmail,
        cursor_store,
        "projects/demo/topics/gmail",
        processed.append,
    )
    worker.initialize()
    message = notification()

    worker.handle_message(message)

    assert [email["id"] for email in processed] == ["message-a", "message-b"]
    assert cursor_store.get("jobs@example.com") == "105"
    assert gmail.list_calls == ["100"]
    assert message.acked


def test_worker_acks_duplicate_notifications_without_reprocessing(tmp_path):
    gmail = FakeGmail()
    cursor_store = HistoryCursorStore(tmp_path / "state.sqlite3")
    worker = GmailPubSubIngestionWorker(
        gmail,
        cursor_store,
        "projects/demo/topics/gmail",
        lambda email: None,
    )
    worker.initialize()
    worker.handle_message(notification())
    duplicate = notification("105")

    worker.handle_message(duplicate)

    assert duplicate.acked
    assert gmail.list_calls == ["100"]


def test_worker_leaves_notification_unacked_and_cursor_unchanged_on_failure(tmp_path):
    gmail = FakeGmail()
    cursor_store = HistoryCursorStore(tmp_path / "state.sqlite3")

    def fail_processing(email):
        raise RuntimeError("processing failed")

    worker = GmailPubSubIngestionWorker(
        gmail,
        cursor_store,
        "projects/demo/topics/gmail",
        fail_processing,
    )
    worker.initialize()
    message = notification()

    with pytest.raises(RuntimeError, match="processing failed"):
        worker.handle_message(message)

    assert cursor_store.get("jobs@example.com") == "100"
    assert not message.acked


def test_worker_rejects_notifications_for_another_account(tmp_path):
    cursor_store = HistoryCursorStore(tmp_path / "state.sqlite3")
    worker = GmailPubSubIngestionWorker(
        FakeGmail(),
        cursor_store,
        "projects/demo/topics/gmail",
        lambda email: None,
    )
    worker.initialize()
    message = notification(email="attacker@example.com")

    with pytest.raises(ValueError, match="does not match"):
        worker.handle_message(message)

    assert not message.acked


def test_worker_closes_resources_when_subscription_is_invalid(tmp_path):
    shutdown_calls = []
    worker = GmailPubSubIngestionWorker(
        FakeGmail(),
        HistoryCursorStore(tmp_path / "state.sqlite3"),
        "projects/demo/topics/gmail",
        lambda email: None,
        on_shutdown=lambda: shutdown_calls.append(True),
    )

    with pytest.raises(ValueError, match="subscription name is required"):
        worker.run(" ")

    assert shutdown_calls == [True]


def test_worker_factory_wires_gmail_messages_through_extraction(
    tmp_path,
    monkeypatch,
):
    gmail = FakeGmail()
    processed = []
    graph_saved = []
    credentials = object()

    class FakeSheetsStore:
        def initialize(self):
            pass

        def save(self, application):
            processed.append(application)

    class FakeGraphStore:
        def initialize(self):
            pass

        def save(self, application):
            graph_saved.append(application)

        def close(self):
            pass

    class FakeExtractor:
        def extract(self, email):
            return JobEmailExtraction(
                is_job_related=True,
                application=ApplicationDetails(
                    company="Example Corp",
                    role="Engineer",
                    status=ApplicationStatus.APPLIED,
                ),
            )

    monkeypatch.setattr(
        "job_tracker.worker.ingestion.build_gmail_client",
        lambda settings: gmail,
    )
    monkeypatch.setattr(
        "job_tracker.worker.ingestion.build_email_extractor",
        lambda settings: FakeExtractor(),
    )
    monkeypatch.setattr(
        "job_tracker.worker.ingestion.build_google_credentials",
        lambda settings: credentials,
    )
    monkeypatch.setattr(
        "job_tracker.worker.ingestion.build_google_sheets_store",
        lambda settings, google_credentials: FakeSheetsStore(),
    )
    monkeypatch.setattr(
        "job_tracker.worker.ingestion.build_neo4j_store",
        lambda settings: FakeGraphStore(),
    )
    settings = Settings(
        _env_file=None,
        google_pubsub_topic="projects/demo/topics/gmail",
        google_pubsub_subscription="projects/demo/subscriptions/jobs",
        google_sheets_spreadsheet_id="spreadsheet-id",
        history_cursor_db=tmp_path / "state.sqlite3",
    )

    worker = build_ingestion_worker(settings)
    worker.initialize()
    message = notification()
    worker.handle_message(message)

    assert [application.source_email_id for application in processed] == [
        "message-a",
        "message-b",
    ]
    assert [application.source_email_id for application in graph_saved] == [
        "message-a",
        "message-b",
    ]
    assert message.acked
