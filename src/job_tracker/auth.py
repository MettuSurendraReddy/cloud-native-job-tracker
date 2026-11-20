"""Command-line entry point for one-time Gmail OAuth authorization."""

from job_tracker.config import get_settings
from job_tracker.integrations.gmail import authorize_gmail


def main() -> None:
    authorize_gmail(get_settings())
    print("Gmail OAuth token saved.")


if __name__ == "__main__":
    main()
