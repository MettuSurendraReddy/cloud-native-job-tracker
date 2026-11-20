"""Parsing helpers for Gmail Pub/Sub push notifications."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class GmailNotification(BaseModel):
    """Validated Gmail mailbox notification carried by a Pub/Sub message."""

    model_config = ConfigDict(extra="forbid")

    email_address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        validation_alias="emailAddress"
    )
    history_id: Annotated[str, StringConstraints(pattern=r"^\d+$")] = Field(
        validation_alias="historyId"
    )

    @field_validator("history_id", mode="before")
    @classmethod
    def normalize_numeric_history_id(cls, value):
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value


def parse_gmail_notification(data: bytes) -> GmailNotification:
    """Decode and validate Pub/Sub message data from Gmail."""

    return GmailNotification.model_validate_json(data)
