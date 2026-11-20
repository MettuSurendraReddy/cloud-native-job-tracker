"""Shared data models for normalized job application updates."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApplicationStatus(StrEnum):
    """Application state inferred from a job-related email."""

    APPLIED = "applied"
    INTERVIEW = "interview"
    ASSESSMENT = "assessment"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"


class ApplicationDetails(BaseModel):
    """Application fields extracted from an email, before adding email metadata."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: NonEmptyText | None
    role: NonEmptyText | None
    status: ApplicationStatus
    location: str | None = None
    job_url: AnyHttpUrl | None = None
    applied_at: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class JobEmailExtraction(BaseModel):
    """Classify an email and optionally return its extracted application details."""

    model_config = ConfigDict(extra="forbid")

    is_job_related: bool
    application: ApplicationDetails | None = None

    @model_validator(mode="after")
    def validate_classification_result(self):
        if self.is_job_related != (self.application is not None):
            raise ValueError(
                "Job-related emails must include application details; non-job emails must not."
            )
        return self


class JobApplication(ApplicationDetails):
    """Normalized application details enriched with source email metadata."""

    email_subject: str | None = None
    email_received_at: datetime | None = None
    source_email_id: NonEmptyText | None = None
