"""Connect Gmail message parsing, LLM extraction, and application handling."""

from collections.abc import Callable
from typing import Any

from job_tracker.integrations.email_parser import parse_gmail_message
from job_tracker.integrations.llm import StructuredEmailExtractor
from job_tracker.models import JobApplication


class EmailExtractionPipeline:
    """Transform raw Gmail API messages into validated job applications."""

    def __init__(
        self,
        extractor: StructuredEmailExtractor,
        on_application: Callable[[JobApplication], object],
        max_body_chars: int = 20_000,
    ) -> None:
        self._extractor = extractor
        self._on_application = on_application
        self._max_body_chars = max_body_chars

    def process(self, message: dict[str, Any]) -> JobApplication | None:
        email = parse_gmail_message(message, max_body_chars=self._max_body_chars)
        result = self._extractor.extract(email)
        if not result.is_job_related:
            return None
        if result.application is None:
            raise RuntimeError("Job-related extraction is missing application details.")

        application = JobApplication(
            **result.application.model_dump(),
            email_subject=email.subject or None,
            email_received_at=email.received_at,
            source_email_id=email.message_id,
        )
        self._on_application(application)
        return application
