from job_tracker.integrations.gmail import GmailClient, load_gmail_credentials


class FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeHistoryResource:
    def __init__(self, responses):
        self._responses = responses
        self.requests = []

    def list(self, **kwargs):
        self.requests.append(kwargs)
        return FakeRequest(self._responses.pop(0))


class FakeUsersResource:
    def __init__(self, history):
        self._history = history

    def history(self):
        return self._history


class FakeGmailService:
    def __init__(self, history):
        self._users = FakeUsersResource(history)

    def users(self):
        return self._users


def test_history_fetch_paginates_and_deduplicates_added_messages():
    history = FakeHistoryResource(
        [
            {
                "historyId": "11",
                "history": [
                    {"messagesAdded": [{"message": {"id": "message-a"}}]},
                    {"messagesAdded": [{"message": {"id": "message-a"}}]},
                ],
                "nextPageToken": "next",
            },
            {
                "historyId": "12",
                "history": [{"messagesAdded": [{"message": {"id": "message-b"}}]}],
            },
        ]
    )
    gmail = GmailClient(FakeGmailService(history))

    message_ids, latest_history_id = gmail.list_message_ids_after("10")

    assert message_ids == ["message-a", "message-b"]
    assert latest_history_id == "12"
    assert history.requests[0]["startHistoryId"] == "10"
    assert history.requests[1]["pageToken"] == "next"


def test_refresh_does_not_rewrite_read_only_oauth_token(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    token_file = tmp_path / "token.json"
    token_file.write_text("original token", encoding="utf-8")

    class FakeCredentials:
        expired = True
        refresh_token = "refresh-token"
        valid = True

        def refresh(self, request):
            self.refreshed = True

    credentials = FakeCredentials()
    monkeypatch.setattr(
        Credentials,
        "from_authorized_user_file",
        lambda *args, **kwargs: credentials,
    )

    assert load_gmail_credentials(token_file) is credentials
    assert credentials.refreshed
    assert token_file.read_text(encoding="utf-8") == "original token"
