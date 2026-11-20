from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from job_tracker.models import (
    ApplicationDetails,
    ApplicationStatus,
    JobApplication,
    JobEmailExtraction,
)


def test_job_application_validates_and_serializes_extracted_data():
    application = JobApplication(
        company="  Example Corp  ",
        role="Senior Engineer",
        status="interview",
        applied_at="2026-11-18",
        email_received_at="2026-11-18T10:30:00Z",
        source_email_id=" message-123 ",
        confidence=0.9,
    )

    assert application.company == "Example Corp"
    assert application.status is ApplicationStatus.INTERVIEW
    assert application.applied_at == date(2026, 11, 18)
    assert application.email_received_at == datetime(2026, 11, 18, 10, 30, tzinfo=UTC)
    assert application.source_email_id == "message-123"
    assert application.model_dump(mode="json")["status"] == "interview"


@pytest.mark.parametrize("field", ["company", "role"])
def test_job_application_rejects_blank_required_text(field):
    values = {"company": "Example Corp", "role": "Engineer", "status": "applied"}
    values[field] = "   "

    with pytest.raises(ValidationError):
        JobApplication(**values)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_job_application_rejects_confidence_outside_zero_to_one(confidence):
    with pytest.raises(ValidationError):
        JobApplication(
            company="Example Corp",
            role="Engineer",
            status="applied",
            confidence=confidence,
        )


def test_job_application_rejects_unknown_status_and_extra_fields():
    with pytest.raises(ValidationError):
        JobApplication(company="Example Corp", role="Engineer", status="hired")

    with pytest.raises(ValidationError):
        JobApplication(
            company="Example Corp",
            role="Engineer",
            status="applied",
            unexpected="value",
        )


def test_job_email_extraction_requires_details_only_for_job_related_emails():
    unrelated = JobEmailExtraction(is_job_related=False)
    related = JobEmailExtraction(
        is_job_related=True,
        application=ApplicationDetails(
            company=None,
            role=None,
            status=ApplicationStatus.UNKNOWN,
        ),
    )

    assert unrelated.application is None
    assert related.application.status is ApplicationStatus.UNKNOWN

    with pytest.raises(ValidationError):
        JobEmailExtraction(is_job_related=True)
