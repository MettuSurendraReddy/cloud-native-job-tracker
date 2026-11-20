"""Idempotent persistence of job applications in Google Sheets."""

from threading import Lock
from typing import Any

from google.auth.credentials import Credentials

from job_tracker.config import Settings
from job_tracker.integrations.google_auth import build_google_credentials
from job_tracker.models import JobApplication

APPLICATION_HEADERS = (
    "source_email_id",
    "company",
    "role",
    "status",
    "location",
    "job_url",
    "applied_at",
    "email_subject",
    "email_received_at",
    "confidence",
    "notes",
)


class GoogleSheetsStore:
    """Append each source email once to a named worksheet."""

    def __init__(self, service: Any, spreadsheet_id: str, worksheet: str) -> None:
        if not spreadsheet_id.strip():
            raise ValueError("A Google Sheets spreadsheet ID is required.")
        if not worksheet.strip():
            raise ValueError("A Google Sheets worksheet name is required.")

        self._service = service
        self._spreadsheet_id = spreadsheet_id
        self._worksheet = worksheet
        self._lock = Lock()
        self._initialized = False

    def initialize(self) -> None:
        """Create the worksheet and header row if they do not already exist."""

        with self._lock:
            self._initialize()

    def _initialize(self) -> None:
        if self._initialized:
            return

        spreadsheet = (
            self._service.spreadsheets()
            .get(
                spreadsheetId=self._spreadsheet_id,
                fields="sheets(properties(title))",
            )
            .execute()
        )
        sheets = spreadsheet.get("sheets", [])
        worksheet_exists = any(
            sheet.get("properties", {}).get("title") == self._worksheet for sheet in sheets
        )

        if not worksheet_exists:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self._spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": self._worksheet}}}]},
            ).execute()

        header_range = f"{self._quoted_worksheet()}!1:1"
        header_response = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self._spreadsheet_id, range=header_range)
            .execute()
        )
        values = header_response.get("values", [])
        if not values:
            self._service.spreadsheets().values().update(
                spreadsheetId=self._spreadsheet_id,
                range=f"{self._quoted_worksheet()}!A1",
                valueInputOption="RAW",
                body={"values": [list(APPLICATION_HEADERS)]},
            ).execute()
        elif values[0] != list(APPLICATION_HEADERS):
            raise ValueError(
                f"Worksheet {self._worksheet!r} has unexpected headers; "
                "expected the job tracker schema."
            )

        self._initialized = True

    def _quoted_worksheet(self) -> str:
        return "'" + self._worksheet.replace("'", "''") + "'"

    def save(self, application: JobApplication) -> bool:
        """Append an application unless its Gmail message ID is already present."""

        if not application.source_email_id:
            raise ValueError("A source Gmail message ID is required for idempotent storage.")

        with self._lock:
            self._initialize()
            existing_ids_response = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"{self._quoted_worksheet()}!A2:A",
                )
                .execute()
            )
            existing_ids = {
                row[0]
                for row in existing_ids_response.get("values", [])
                if row and isinstance(row[0], str)
            }
            if application.source_email_id in existing_ids:
                return False

            serialized = application.model_dump(mode="json")
            row = []
            for header in APPLICATION_HEADERS:
                value = serialized.get(header)
                row.append("" if value is None else value)
            self._service.spreadsheets().values().append(
                spreadsheetId=self._spreadsheet_id,
                range=f"{self._quoted_worksheet()}!A:K",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()
            return True


def build_google_sheets_store(
    settings: Settings,
    credentials: Credentials | None = None,
) -> GoogleSheetsStore:
    """Create the Sheets API-backed store using ADC or a configured service account."""

    if not settings.google_sheets_spreadsheet_id:
        raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be configured.")

    from googleapiclient.discovery import build

    credentials = credentials or build_google_credentials(settings)
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return GoogleSheetsStore(
        service,
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        worksheet=settings.google_sheets_worksheet,
    )
