"""Pub/Sub-driven Gmail history ingestion."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

from job_tracker.config import Settings
from job_tracker.integrations.gmail import GmailClient, build_gmail_client
from job_tracker.integrations.google_auth import build_google_credentials
from job_tracker.integrations.llm import build_email_extractor
from job_tracker.integrations.neo4j_store import build_neo4j_store
from job_tracker.integrations.pubsub import parse_gmail_notification
from job_tracker.integrations.sheets import build_google_sheets_store
from job_tracker.models import JobApplication
from job_tracker.worker.pipeline import EmailExtractionPipeline


class PubSubMessage(Protocol):
    data: bytes

    def ack(self) -> None: ...


class HistoryCursorStore:
    """Persist the last completely processed Gmail history ID in SQLite."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._database_path)) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_history_cursor (
                    account TEXT PRIMARY KEY,
                    history_id TEXT NOT NULL
                )
                """
            )

    def get(self, account: str) -> str | None:
        with closing(sqlite3.connect(self._database_path)) as connection:
            row = connection.execute(
                "SELECT history_id FROM gmail_history_cursor WHERE account = ?",
                (account,),
            ).fetchone()
        return row[0] if row else None

    def save(self, account: str, history_id: str) -> None:
        if not history_id.isdigit():
            raise ValueError("Gmail history ID must contain only digits.")

        with closing(sqlite3.connect(self._database_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO gmail_history_cursor (account, history_id)
                VALUES (?, ?)
                ON CONFLICT(account) DO UPDATE SET history_id = excluded.history_id
                """,
                (account, history_id),
            )


class GmailPubSubIngestionWorker:
    """Fetch Gmail changes and dispatch messages before acknowledging Pub/Sub."""

    def __init__(
        self,
        gmail: GmailClient,
        cursor_store: HistoryCursorStore,
        pubsub_topic: str,
        on_email: Callable[[dict[str, Any]], object],
        pubsub_credentials: Any = None,
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self._gmail = gmail
        self._cursor_store = cursor_store
        self._pubsub_topic = pubsub_topic
        self._on_email = on_email
        self._pubsub_credentials = pubsub_credentials
        self._on_shutdown = on_shutdown
        self._account: str | None = None
        self._lock = Lock()

    def initialize(self) -> None:
        """Register Gmail notifications and initialize the history cursor once."""

        profile = self._gmail.get_profile()
        account = profile.get("emailAddress")
        if not isinstance(account, str) or not account.strip():
            raise RuntimeError("Gmail profile response did not contain an email address.")

        watch = self._gmail.start_watch(self._pubsub_topic)
        watch_history_id = watch.get("historyId")
        if not isinstance(watch_history_id, str) or not watch_history_id.isdigit():
            raise RuntimeError("Gmail watch response did not contain a valid history ID.")

        normalized_account = account.casefold()
        with self._lock:
            if self._cursor_store.get(normalized_account) is None:
                self._cursor_store.save(normalized_account, watch_history_id)
            self._account = normalized_account

    def run(self, subscription: str) -> None:
        """Run the Pub/Sub subscriber, renewing Gmail's expiring watch daily."""

        subscriber = None
        streaming_pull = None
        try:
            if not subscription.strip():
                raise ValueError("A fully qualified Pub/Sub subscription name is required.")

            from concurrent.futures import TimeoutError as FutureTimeoutError

            from google.cloud import pubsub_v1

            self.initialize()
            subscriber = pubsub_v1.SubscriberClient(credentials=self._pubsub_credentials)
            streaming_pull = subscriber.subscribe(
                subscription,
                callback=self.handle_message,
            )
            while True:
                try:
                    streaming_pull.result(timeout=24 * 60 * 60)
                    return
                except FutureTimeoutError:
                    self._gmail.start_watch(self._pubsub_topic)
        except KeyboardInterrupt:
            if streaming_pull is not None:
                streaming_pull.cancel()
        finally:
            try:
                if subscriber is not None:
                    subscriber.close()
            finally:
                if self._on_shutdown is not None:
                    self._on_shutdown()

    def handle_message(self, message: PubSubMessage) -> None:
        """Process one Gmail notification; leave it unacked on any processing error."""

        notification = parse_gmail_notification(message.data)
        with self._lock:
            if self._account is None:
                raise RuntimeError("Initialize the Gmail ingestion worker before use.")
            if notification.email_address.casefold() != self._account:
                raise ValueError(
                    "Gmail notification account does not match the authorized account."
                )

            current_history_id = self._cursor_store.get(self._account)
            if current_history_id is None:
                raise RuntimeError("Gmail history cursor has not been initialized.")
            if int(notification.history_id) <= int(current_history_id):
                message.ack()
                return

            message_ids, latest_history_id = self._gmail.list_message_ids_after(current_history_id)
            for message_id in message_ids:
                self._on_email(self._gmail.get_message(message_id))

            next_history_id = max(
                notification.history_id,
                latest_history_id,
                key=int,
            )
            self._cursor_store.save(self._account, next_history_id)

        message.ack()


def build_ingestion_worker(settings: Settings) -> GmailPubSubIngestionWorker:
    """Create an ingestion worker wired to extraction and Google Sheets persistence."""

    if not settings.google_pubsub_topic.strip():
        raise ValueError("GOOGLE_PUBSUB_TOPIC must be configured.")
    if not settings.google_pubsub_subscription.strip():
        raise ValueError("GOOGLE_PUBSUB_SUBSCRIPTION must be configured.")
    if not settings.google_sheets_spreadsheet_id.strip():
        raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be configured.")

    extractor = build_email_extractor(settings)
    credentials = build_google_credentials(settings)

    from contextlib import ExitStack

    with ExitStack() as cleanup:
        graph_store = build_neo4j_store(settings)
        cleanup.callback(graph_store.close)
        graph_store.initialize()

        sheets_store = build_google_sheets_store(settings, credentials)
        sheets_store.initialize()

        def persist_application(application: JobApplication) -> None:
            sheets_store.save(application)
            graph_store.save(application)

        pipeline = EmailExtractionPipeline(
            extractor=extractor,
            on_application=persist_application,
            max_body_chars=settings.llm_email_body_max_chars,
        )
        gmail = build_gmail_client(settings)
        cursor_store = HistoryCursorStore(settings.history_cursor_db)
        resource_cleanup = cleanup.pop_all()
        worker = GmailPubSubIngestionWorker(
            gmail=gmail,
            cursor_store=cursor_store,
            pubsub_topic=settings.google_pubsub_topic,
            on_email=pipeline.process,
            pubsub_credentials=credentials,
            on_shutdown=resource_cleanup.close,
        )
        return worker
