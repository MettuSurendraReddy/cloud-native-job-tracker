from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from job_tracker.config import Settings
from job_tracker.integrations.email_parser import GmailEmail
from job_tracker.integrations.llm import (
    EmailExtractionError,
    GeminiProvider,
    GroqProvider,
    ProviderError,
    StructuredEmailExtractor,
    build_email_extractor,
)
from job_tracker.models import (
    ApplicationDetails,
    ApplicationStatus,
    JobEmailExtraction,
)


def job_result():
    return JobEmailExtraction(
        is_job_related=True,
        application=ApplicationDetails(
            company="Example Corp",
            role="Backend Engineer",
            status=ApplicationStatus.INTERVIEW,
            confidence=0.93,
        ),
    )


class FakeProvider:
    name = "Fake"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def extract(self, email):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_extractor_uses_groq_fallback_when_gemini_fails():
    primary = FakeProvider(error=ProviderError("Gemini failed"))
    fallback = FakeProvider(result=job_result())
    extractor = StructuredEmailExtractor(primary, fallback)
    email = GmailEmail("id", "subject", "sender", None, "body")

    result = extractor.extract(email)

    assert result.application.company == "Example Corp"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_extractor_raises_when_both_providers_fail():
    extractor = StructuredEmailExtractor(
        FakeProvider(error=ProviderError("Gemini failed")),
        FakeProvider(error=ProviderError("Groq failed")),
    )

    with pytest.raises(EmailExtractionError, match="extraction failed"):
        extractor.extract(GmailEmail("id", "", "", None, "body"))


def test_provider_response_decoding_and_groq_request_shape():
    expected = job_result()
    observed = {}

    def create_completion(**kwargs):
        observed.update(kwargs)
        return groq_response

    groq_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=expected.model_dump_json()))]
    )
    groq_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion))
    )
    provider = GroqProvider("unused", "test-model", client=groq_client)

    result = provider.extract(GmailEmail("id", "subject", "sender", None, "body"))

    assert result == expected
    assert "json" in " ".join(message["content"] for message in observed["messages"]).lower()
    assert observed["response_format"] == {"type": "json_object"}


def test_gemini_provider_uses_structured_response_schema():
    expected = job_result()
    observed = {}

    def generate_content(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(parsed=expected, text=None)

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider = GeminiProvider("unused", "test-model", client=client)

    result = provider.extract(
        GmailEmail("id", "subject", "sender", datetime(2026, 1, 1, tzinfo=UTC), "body")
    )

    assert result == expected
    assert observed["model"] == "test-model"
    assert observed["config"].response_schema is JobEmailExtraction


def test_build_extractor_requires_a_provider_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY or GROQ_API_KEY"):
        build_email_extractor(Settings(_env_file=None))


def test_build_extractor_treats_blank_api_keys_as_missing():
    settings = Settings(_env_file=None, gemini_api_key=" ", groq_api_key="")

    with pytest.raises(ValueError, match="GEMINI_API_KEY or GROQ_API_KEY"):
        build_email_extractor(settings)


def test_build_extractor_prefers_gemini_and_configures_groq_fallback():
    extractor = build_email_extractor(
        Settings(
            _env_file=None,
            gemini_api_key="gemini-test-key",
            groq_api_key="groq-test-key",
        )
    )

    assert extractor._primary.name == "Gemini"
    assert extractor._fallback.name == "Groq"
