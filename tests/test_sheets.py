import pytest

from job_tracker.integrations.sheets import APPLICATION_HEADERS, GoogleSheetsStore
from job_tracker.models import ApplicationStatus, JobApplication


class FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeValuesApi:
    def __init__(self, headers=None):
        self.headers = headers or []
        self.rows = []
        self.append_options = []

    def get(self, spreadsheetId, range):
        if range.endswith("!1:1"):
            values = [self.headers] if self.headers else []
        elif range.endswith("!A2:A"):
            values = [[row[0]] for row in self.rows]
        else:
            raise AssertionError(f"Unexpected read range: {range}")
        return FakeRequest({"values": values})

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.headers = body["values"][0]
        return FakeRequest({})

    def append(self, spreadsheetId, range, valueInputOption, insertDataOption, body):
        self.append_options.append((valueInputOption, insertDataOption))
        self.rows.extend(body["values"])
        return FakeRequest({})


class FakeSpreadsheetsApi:
    def __init__(self, values_api, worksheets=None):
        self._values_api = values_api
        self.worksheets = worksheets or []

    def get(self, spreadsheetId, fields):
        return FakeRequest(
            {"sheets": [{"properties": {"title": title}} for title in self.worksheets]}
        )

    def batchUpdate(self, spreadsheetId, body):
        title = body["requests"][0]["addSheet"]["properties"]["title"]
        self.worksheets.append(title)
        return FakeRequest({})

    def values(self):
        return self._values_api


class FakeSheetsService:
    def __init__(self, headers=None, worksheets=None):
        self.values_api = FakeValuesApi(headers=headers)
        self.spreadsheets_api = FakeSpreadsheetsApi(self.values_api, worksheets)

    def spreadsheets(self):
        return self.spreadsheets_api


def test_sheets_store_creates_schema_and_appends_each_message_once():
    service = FakeSheetsService()
    store = GoogleSheetsStore(service, "spreadsheet-id", "Applications")
    application = JobApplication(
        source_email_id="gmail-123",
        company="Example Corp",
        role="Engineer",
        status=ApplicationStatus.APPLIED,
        confidence=0,
        notes="=not a formula",
    )

    store.initialize()
    assert service.values_api.headers == list(APPLICATION_HEADERS)
    assert store.save(application)
    assert not store.save(application)

    assert len(service.values_api.rows) == 1
    assert service.values_api.rows[0][0] == "gmail-123"
    assert service.values_api.rows[0][9] == 0
    assert service.values_api.rows[0][10] == "=not a formula"
    assert service.values_api.append_options == [("RAW", "INSERT_ROWS")]


def test_sheets_store_rejects_a_worksheet_with_unexpected_headers():
    service = FakeSheetsService(headers=["old schema"], worksheets=["Applications"])
    store = GoogleSheetsStore(service, "spreadsheet-id", "Applications")

    with pytest.raises(ValueError, match="unexpected headers"):
        store.initialize()


def test_sheets_store_requires_source_message_id():
    store = GoogleSheetsStore(FakeSheetsService(), "spreadsheet-id", "Applications")
    application = JobApplication(
        company="Example Corp",
        role="Engineer",
        status=ApplicationStatus.APPLIED,
    )

    with pytest.raises(ValueError, match="source Gmail message ID"):
        store.save(application)
