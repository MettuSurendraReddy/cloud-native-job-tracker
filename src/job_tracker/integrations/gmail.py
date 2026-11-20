"""Gmail OAuth setup and API operations used by the ingestion worker."""

from pathlib import Path
from typing import Any

from job_tracker.config import Settings

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def authorize_gmail(settings: Settings) -> None:
    """Run the one-time local OAuth consent flow and save a refreshable token."""

    from google_auth_oauthlib.flow import InstalledAppFlow

    if not settings.gmail_client_secrets_file.is_file():
        raise FileNotFoundError(
            f"Gmail OAuth client file not found: {settings.gmail_client_secrets_file}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(settings.gmail_client_secrets_file),
        scopes=[GMAIL_READONLY_SCOPE],
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    settings.gmail_token_file.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_file.write_text(credentials.to_json(), encoding="utf-8")


def load_gmail_credentials(token_file: Path) -> Any:
    """Load a saved OAuth token, refreshing its access token in memory when needed."""

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not token_file.is_file():
        raise FileNotFoundError(
            f"Gmail OAuth token not found: {token_file}. "
            "Run `python -m job_tracker.auth` to authorize Gmail."
        )

    credentials = Credentials.from_authorized_user_file(
        str(token_file),
        scopes=[GMAIL_READONLY_SCOPE],
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials.valid:
        raise RuntimeError(
            f"Gmail OAuth token is invalid: {token_file}. "
            "Run `python -m job_tracker.auth` to authorize Gmail again."
        )
    return credentials


class GmailClient:
    """Small wrapper around the Gmail API service resource."""

    def __init__(self, service: Any, user_id: str = "me") -> None:
        self._service = service
        self._user_id = user_id

    def get_profile(self) -> dict[str, Any]:
        return self._service.users().getProfile(userId=self._user_id).execute()

    def start_watch(self, topic_name: str) -> dict[str, Any]:
        return (
            self._service.users()
            .watch(userId=self._user_id, body={"topicName": topic_name})
            .execute()
        )

    def list_message_ids_after(self, history_id: str) -> tuple[list[str], str]:
        """Return unique newly-added message IDs and the latest Gmail history ID."""

        if not history_id.isdigit():
            raise ValueError("Gmail history ID must contain only digits.")

        message_ids: dict[str, None] = {}
        page_token = None
        latest_history_id = ""
        while True:
            request = (
                self._service.users()
                .history()
                .list(
                    userId=self._user_id,
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    pageToken=page_token,
                )
            )
            response = request.execute()
            current_history_id = response.get("historyId")
            if not isinstance(current_history_id, str) or not current_history_id.isdigit():
                raise RuntimeError("Gmail history response did not contain a valid history ID.")
            latest_history_id = current_history_id

            for record in response.get("history", []):
                for added in record.get("messagesAdded", []):
                    message = added.get("message", {})
                    message_id = message.get("id")
                    if isinstance(message_id, str) and message_id:
                        message_ids.setdefault(message_id, None)

            page_token = response.get("nextPageToken")
            if not page_token:
                return list(message_ids), latest_history_id

    def get_message(self, message_id: str) -> dict[str, Any]:
        return (
            self._service.users()
            .messages()
            .get(userId=self._user_id, id=message_id, format="full")
            .execute()
        )


def build_gmail_client(settings: Settings) -> GmailClient:
    """Build an authenticated Gmail API client using saved OAuth credentials."""

    from googleapiclient.discovery import build

    credentials = load_gmail_credentials(settings.gmail_token_file)
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    return GmailClient(service, user_id=settings.gmail_user_id)
