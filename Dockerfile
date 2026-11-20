FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HISTORY_CURSOR_DB=/var/lib/job-tracker/tracker.sqlite3

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && useradd --system --uid 10001 --create-home job-tracker \
    && mkdir -p /var/lib/job-tracker \
    && chown job-tracker:job-tracker /var/lib/job-tracker

USER 10001:10001

ENTRYPOINT ["job-tracker-worker"]
