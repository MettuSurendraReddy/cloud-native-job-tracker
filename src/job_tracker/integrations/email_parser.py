"""Extract readable headers and body text from Gmail API messages."""

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any


@dataclass(frozen=True)
class GmailEmail:
    message_id: str
    subject: str
    sender: str
    received_at: datetime | None
    body: str


class EmailParseError(ValueError):
    """Raised when a Gmail message cannot be decoded into email content."""


class _HTMLTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._text: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._hidden_depth += 1
        elif tag in {"br", "div", "p", "li", "tr"} and not self._hidden_depth:
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag in {"div", "p", "li", "tr"} and not self._hidden_depth:
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self._text.append(data)

    def text(self) -> str:
        return "".join(self._text)


def _decode_header(value: str) -> str:
    decoded_parts = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            decoded_parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(fragment)
    return "".join(decoded_parts).strip()


def _header_value(headers: list[dict[str, Any]], name: str) -> str:
    for header in headers:
        if str(header.get("name", "")).casefold() == name.casefold():
            value = header.get("value", "")
            return _decode_header(value) if isinstance(value, str) else ""
    return ""


def _part_body(data: str) -> str:
    padded_data = data + ("=" * (-len(data) % 4))
    try:
        decoded = base64.b64decode(padded_data, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise EmailParseError("Gmail message body contains invalid base64 data.") from error
    return decoded.decode("utf-8", errors="replace")


def _append_text_parts(
    part: dict[str, Any],
    plain_text: list[str],
    html_text: list[str],
    max_chars: int,
) -> None:
    if part.get("filename"):
        return

    children = part.get("parts", [])
    if isinstance(children, list) and children:
        for child in children:
            if isinstance(child, dict):
                _append_text_parts(child, plain_text, html_text, max_chars)
        return

    mime_type = part.get("mimeType")
    target = (
        plain_text if mime_type == "text/plain" else html_text if mime_type == "text/html" else None
    )
    body = part.get("body", {})
    data = body.get("data") if isinstance(body, dict) else None
    if target is None or not isinstance(data, str):
        return

    remaining = max_chars - sum(len(text) for text in plain_text + html_text)
    if remaining > 0:
        text = _part_body(data)
        if mime_type == "text/html":
            text = _html_to_text(text)
        target.append(text[:remaining])


def _html_to_text(value: str) -> str:
    parser = _HTMLTextParser()
    parser.feed(value)
    parser.close()
    return parser.text()


def _normalize_body(value: str, max_chars: int) -> str:
    lines = [line.strip() for line in value.replace("\r", "\n").split("\n")]
    normalized = "\n".join(line for line in lines if line)
    return normalized[:max_chars].rstrip()


def _received_at(message: dict[str, Any], headers: list[dict[str, Any]]) -> datetime | None:
    internal_date = message.get("internalDate")
    if isinstance(internal_date, (str, int)) and str(internal_date).isdigit():
        try:
            return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            pass

    date_header = _header_value(headers, "Date")
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header)
        except (TypeError, ValueError, OverflowError):
            return None
        if received_at.tzinfo is None:
            return received_at.replace(tzinfo=UTC)
        return received_at
    return None


def parse_gmail_message(message: dict[str, Any], max_body_chars: int = 20_000) -> GmailEmail:
    """Decode a Gmail API message, preferring plain text over HTML."""

    if max_body_chars < 1:
        raise ValueError("max_body_chars must be a positive integer.")

    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id.strip():
        raise EmailParseError("Gmail message does not contain a message ID.")

    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        headers = []

    plain_text: list[str] = []
    html_text: list[str] = []
    _append_text_parts(payload, plain_text, html_text, max_body_chars)
    body = "\n".join(plain_text) if plain_text else "\n".join(html_text)

    return GmailEmail(
        message_id=message_id.strip(),
        subject=_header_value(headers, "Subject"),
        sender=_header_value(headers, "From"),
        received_at=_received_at(message, headers),
        body=_normalize_body(body, max_body_chars),
    )
