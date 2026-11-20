# Cloud-Native Job Application Tracker

A Python service for processing job-related email, extracting structured application
updates, and making them available in Google Sheets and a Neo4j graph.

## Project layout

```text
src/job_tracker/
  config.py       Environment-backed runtime settings
  integrations/   Gmail, Pub/Sub, LLM, Sheets, and Neo4j adapters
  mcp_server/     FastMCP tools for querying tracker data
  auth.py         Local Gmail OAuth authorization
  models.py       Shared validated job application schema
  worker/         Gmail ingestion and structured extraction pipeline
tests/            Automated tests
Dockerfile        Container image for the ingestion worker
compose.yaml      Local and OCI worker deployment
infra/oci/        OCI Compute deployment instructions
```

## Getting started

Requirements: Python 3.11 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

For Gmail authorization, enable the Gmail API, create a Desktop OAuth client, and
save its JSON as `credentials.json` (or set `GMAIL_CLIENT_SECRETS_FILE`). After
installing the project, run `python -m job_tracker.auth` from the project root and
complete the browser consent flow. This creates the ignored `token.json` file.

Configure `GOOGLE_PUBSUB_TOPIC` and `GOOGLE_PUBSUB_SUBSCRIPTION` with their full
Google Cloud resource names. Enable the Sheets API, set `GOOGLE_SHEETS_SPREADSHEET_ID`,
and optionally choose `GOOGLE_SHEETS_WORKSHEET`. Configure a service account file in
`GOOGLE_APPLICATION_CREDENTIALS` (keep local key files under the ignored `.secrets/`
folder) or use runtime Application Default Credentials. Give that account Pub/Sub
subscriber access and edit access to the spreadsheet; grant Gmail permission to
publish to the Pub/Sub topic.

Create the worker with `settings = get_settings()` and
`worker = build_ingestion_worker(settings)`, then call
`worker.run(settings.google_pubsub_subscription)`. It registers and renews Gmail watch
notifications, reads message changes from Gmail history, extracts applications, and
stores them in Sheets and Neo4j. A source Gmail message ID is used to avoid duplicate
rows and graph nodes on Pub/Sub redelivery. The local SQLite cursor advances only
after processing succeeds, so the Pub/Sub message remains eligible for redelivery if
extraction or storage fails.

Set `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` for the
worker's graph writer. The worker creates uniqueness constraints and stores
`JobApplication`, `Company`, and `JobRole` nodes with relationships. For MCP, set the
separate `NEO4J_MCP_USERNAME` and `NEO4J_MCP_PASSWORD` to a database user granted
read-only access.

The MCP server exposes only bounded search and get tools and runs over local stdio:
`python -m job_tracker.mcp_server` or `job-tracker-mcp`. To access a private Neo4j
host through an OCI bastion, start an SSH local port forward before launching the
MCP server from Claude Desktop:

```powershell
ssh -N -L 7687:<neo4j-private-host>:7687 <ssh-user>@<oci-bastion>
```

Set `NEO4J_URI=bolt://127.0.0.1:7687` for that tunnel. For a directly reachable
encrypted Neo4j endpoint, use its `neo4j+s://` URI instead. The MCP process uses the
read-only Neo4j credentials locally; it does not expose a network listener.

Set `GEMINI_API_KEY` and/or `GROQ_API_KEY`; Gemini is preferred when both are
configured, with Groq used if Gemini fails. Model names and the maximum email body
sent for extraction are configurable in `.env`. Email content is sent to the
configured LLM provider, so review its data handling policy before processing
personal mail.

## Run the worker in Docker

Create `.env` from `.env.example`, then place the Google service-account JSON,
Gmail OAuth client JSON, and Gmail token JSON under `.secrets/` using the filenames
shown in `compose.yaml`. The Compose file mounts these credentials read-only and
persists the SQLite history cursor in a named volume. Refreshed Gmail access tokens
remain in memory; the read-only OAuth token file is not rewritten.

```powershell
docker compose up --build -d
docker compose logs -f worker
```

The worker exposes no inbound port. For OCI Compute deployment, follow
[infra/oci/README.md](infra/oci/README.md). The MCP server remains a separate local
stdio process and is not included in the worker container.

Do not commit `.env`, Google credentials, OAuth tokens, or private keys. The example
environment file contains variable names only; cloud resources and credentials must
be configured separately.

## Implementation stages

1. Define and test the shared application data model (complete).
2. Connect the ingestion worker to structured email extraction (complete).
3. Add Gemini extraction with Groq fallback (complete).
4. Persist validated application updates to Google Sheets (complete).
5. Add Neo4j relationships and read-only FastMCP tools (complete).
6. Containerize the worker and document OCI Compute deployment (container complete;
   cloud resources still require account setup).

Each cloud integration requires its own Google Cloud/OCI resources and credentials.
Those are intentionally not created or assumed by this starter scaffold.
