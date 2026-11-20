import base64
from datetime import UTC, datetime

from job_tracker.integrations.email_parser import parse_gmail_message


def encoded(value):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def test_parser_extracts_headers_plain_text_and_internal_date():
    message = {
        "id": "gmail-123",
        "internalDate": "1795026600000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "=?utf-8?b?QXBwbGljYXRpb24gcmVjZWl2ZWQ=?="},
                {"name": "From", "value": "recruiting@example.com"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": encoded("We received your application.")},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": encoded("<p>HTML fallback</p>")},
                        },
                    ],
                },
                {
                    "mimeType": "text/plain",
                    "filename": "attachment.txt",
                    "body": {"data": encoded("Do not include this attachment.")},
                },
            ],
        },
    }

    email = parse_gmail_message(message)

    assert email.message_id == "gmail-123"
    assert email.subject == "Application received"
    assert email.sender == "recruiting@example.com"
    assert email.body == "We received your application."
    assert email.received_at == datetime.fromtimestamp(1795026600, tz=UTC)


def test_parser_converts_html_and_applies_body_limit():
    message = {
        "id": "gmail-456",
        "payload": {
            "mimeType": "text/html",
            "body": {
                "data": encoded(
                    "<p>Interview scheduled</p><script>hidden secret</script><p>Tomorrow</p>"
                )
            },
        },
    }

    email = parse_gmail_message(message, max_body_chars=20)

    assert email.body == "Interview scheduled"
    assert "hidden secret" not in email.body
