from types import SimpleNamespace

import pytest

from job_tracker.worker import __main__ as worker_cli


def test_worker_cli_runs_with_configured_subscription(monkeypatch):
    calls = []

    class FakeWorker:
        def run(self, subscription):
            calls.append(subscription)

    monkeypatch.setattr(
        worker_cli,
        "get_settings",
        lambda: SimpleNamespace(google_pubsub_subscription="projects/demo/subscriptions/jobs"),
    )
    monkeypatch.setattr(worker_cli, "build_ingestion_worker", lambda settings: FakeWorker())

    worker_cli.main()

    assert calls == ["projects/demo/subscriptions/jobs"]


def test_worker_cli_rejects_missing_subscription(monkeypatch):
    monkeypatch.setattr(
        worker_cli,
        "get_settings",
        lambda: SimpleNamespace(google_pubsub_subscription=" "),
    )

    with pytest.raises(ValueError, match="GOOGLE_PUBSUB_SUBSCRIPTION"):
        worker_cli.main()
