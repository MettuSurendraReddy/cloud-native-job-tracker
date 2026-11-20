"""Command-line entry point for the Pub/Sub ingestion worker."""

from job_tracker.config import get_settings
from job_tracker.worker.ingestion import build_ingestion_worker


def main() -> None:
    settings = get_settings()
    subscription = settings.google_pubsub_subscription
    if not subscription or not subscription.strip():
        raise ValueError("GOOGLE_PUBSUB_SUBSCRIPTION must be configured.")

    build_ingestion_worker(settings).run(subscription)


if __name__ == "__main__":
    main()
