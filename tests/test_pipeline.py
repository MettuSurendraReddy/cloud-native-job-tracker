from datetime import UTC, datetime

from job_tracker.models import ApplicationDetails, ApplicationStatus, JobEmailExtraction
from job_tracker.worker.pipeline import EmailExtractionPipeline


class FakeExtractor:
    def __init__(self, result):
        self.result = result
        self.email = None

    def extract(self, email):
        self.email = email
        return self.result


def raw_message():
    return {
        "id": "gmail-789",
        "internalDate": "1795026600000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Interview invitation"},
                {"name": "From", "value": "recruiting@example.com"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "SW50ZXJ2aWV3IHRvbW9ycm93"},
        },
    }


def test_pipeline_adds_gmail_metadata_and_calls_application_handler():
    extractor = FakeExtractor(
        JobEmailExtraction(
            is_job_related=True,
            application=ApplicationDetails(
                company="Example Corp",
                role="Engineer",
                status=ApplicationStatus.INTERVIEW,
            ),
        )
    )
    applications = []
    pipeline = EmailExtractionPipeline(extractor, applications.append)

    result = pipeline.process(raw_message())

    assert result is applications[0]
    assert result.source_email_id == "gmail-789"
    assert result.email_subject == "Interview invitation"
    assert result.email_received_at == datetime.fromtimestamp(1795026600, tz=UTC)
    assert extractor.email.body == "Interview tomorrow"


def test_pipeline_skips_non_job_emails():
    extractor = FakeExtractor(JobEmailExtraction(is_job_related=False))
    applications = []
    pipeline = EmailExtractionPipeline(extractor, applications.append)

    result = pipeline.process(raw_message())

    assert result is None
    assert applications == []
