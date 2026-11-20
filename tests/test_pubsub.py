import pytest
from pydantic import ValidationError

from job_tracker.integrations.pubsub import parse_gmail_notification


def test_parse_gmail_notification_validates_payload_fields():
    notification = parse_gmail_notification(
        b'{"emailAddress":" jobs@example.com ","historyId":"12345"}'
    )

    assert notification.email_address == "jobs@example.com"
    assert notification.history_id == "12345"


def test_parse_gmail_notification_accepts_integer_history_id():
    notification = parse_gmail_notification(
        b'{"emailAddress":"jobs@example.com","historyId":2168736}'
    )

    assert notification.history_id == "2168736"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"emailAddress":"jobs@example.com","historyId":"not-a-number"}',
        b'{"emailAddress":"jobs@example.com","historyId":"123","unexpected":true}',
    ],
)
def test_parse_gmail_notification_rejects_malformed_payloads(payload):
    with pytest.raises(ValidationError):
        parse_gmail_notification(payload)
