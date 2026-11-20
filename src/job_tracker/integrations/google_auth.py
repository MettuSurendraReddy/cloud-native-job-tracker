"""Google Cloud credentials shared by Pub/Sub and Sheets integrations."""

from google.auth import default, load_credentials_from_file
from google.auth.credentials import Credentials

from job_tracker.config import Settings

GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/pubsub",
    "https://www.googleapis.com/auth/spreadsheets",
)


def build_google_credentials(settings: Settings) -> Credentials:
    """Load a configured service account or use Google Application Default Credentials."""

    credentials_file = settings.google_application_credentials
    if credentials_file is not None:
        if not credentials_file.is_file():
            raise FileNotFoundError(f"Google credentials file not found: {credentials_file}")
        credentials, _ = load_credentials_from_file(
            str(credentials_file),
            scopes=GOOGLE_SCOPES,
        )
        return credentials

    credentials, _ = default(scopes=GOOGLE_SCOPES)
    return credentials
