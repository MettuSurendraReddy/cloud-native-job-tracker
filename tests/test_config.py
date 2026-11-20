from job_tracker.config import Settings


def test_settings_load_pubsub_environment_variables(monkeypatch):
    monkeypatch.setenv("GOOGLE_PUBSUB_SUBSCRIPTION", "projects/demo/subscriptions/jobs")
    monkeypatch.setenv("GOOGLE_PUBSUB_TOPIC", "projects/demo/topics/gmail")
    monkeypatch.setenv("GMAIL_USER_ID", "me")

    settings = Settings(_env_file=None)

    assert settings.google_pubsub_subscription == "projects/demo/subscriptions/jobs"
    assert settings.google_pubsub_topic == "projects/demo/topics/gmail"
    assert settings.gmail_user_id == "me"
