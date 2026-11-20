# OCI Compute deployment

This deployment runs the Pub/Sub worker on one OCI Compute instance with Docker
Compose. The worker initiates outbound connections to Google APIs, the configured
LLM provider, and Neo4j; it does not listen on an inbound port. Cloud resources are
not provisioned automatically by this repository.

## Provision the instance

1. Create a VCN with a private subnet for the Compute instance and a NAT Gateway for
   outbound internet access. Do not assign a public IP to the worker.
2. Provide administrative access using OCI Bastion or an existing private
   management network. Do not open application ports or Neo4j Bolt ports to the
   internet.
3. Use a supported Ubuntu LTS image and install Docker Engine with the Compose
   plugin using Docker's official installation instructions. Confirm
   `docker compose version` works before deploying.
4. Ensure the instance can reach Google Pub/Sub, Gmail, Sheets, the selected LLM
   endpoint, and the Neo4j endpoint. For a private Neo4j deployment, allow Bolt
   traffic only from this worker's private network identity.

## Configure Google and the application

1. Enable Gmail API, Pub/Sub, and Sheets API in the Google Cloud project.
2. Create the Pub/Sub topic and subscription. Configure Gmail push notifications for
   the topic, granting `gmail-api-push@system.gserviceaccount.com` publisher
   permission.
3. Create a Google service account with Pub/Sub subscriber access and edit access to
   the target spreadsheet. Create a Gmail OAuth client and authorize the mailbox
   locally with offline access to produce the OAuth token file. Do not attempt to
   complete the interactive consent flow on the headless Compute instance.
4. Clone this project on the instance. Create `.env` from `.env.example` and fill
   in the topic, subscription, spreadsheet ID, LLM key, Neo4j writer credentials,
   and other required values.
5. Store the service-account JSON, Gmail OAuth client JSON, and Gmail token JSON in
   `.secrets/` with restrictive filesystem permissions. Compose mounts these three
   files read-only into the container. Do not commit the files or put them in the
   image. The `.env` file contains LLM and Neo4j secrets, so restrict its
   permissions as well; for production, prefer an OCI Vault-backed secret delivery
   process rather than leaving long-lived secrets in a local environment file.
6. Start the worker:

   ```sh
   docker compose up --build -d
   docker compose logs -f worker
   ```

The Compose service restarts after process failure and stores the Gmail history
cursor in a named Docker volume. Back up that volume as part of the instance's
recovery plan. Inspect logs and Pub/Sub unacknowledged-message metrics during
operation; the worker intentionally leaves messages unacknowledged when extraction
or persistence fails.

## Connect Claude Desktop to Neo4j

Run the MCP server on the machine where Claude Desktop is installed, not in the
worker container. Use the separate Neo4j read-only account. If Neo4j is private,
create an SSH local forward through the OCI Bastion or an approved jump host, then
set the local MCP process's `NEO4J_URI` to `bolt://127.0.0.1:7687`. Restrict access
to the forward to the authorized operator; never expose Bolt publicly.

## Operational limits

- This single-instance deployment is intended for one worker. Do not scale multiple
  workers against the same SQLite cursor file.
- Docker Compose file-backed secrets are read-only mounts, not a managed secrets
  service. Protect the instance, its disk, `.env`, and `.secrets/`; use OCI Vault
  integration for stronger production secret lifecycle management.
- OCI, Google Cloud, and Neo4j resources, IAM policies, firewall rules, and billing
  are user-managed. No live cloud deployment is performed by the project setup.
