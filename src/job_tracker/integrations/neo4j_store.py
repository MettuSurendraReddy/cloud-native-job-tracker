"""Neo4j persistence and read-only application queries."""

from typing import Any

from neo4j import READ_ACCESS, GraphDatabase
from neo4j.exceptions import Neo4jError

from job_tracker.config import Settings
from job_tracker.models import ApplicationStatus, JobApplication

_CREATE_CONSTRAINTS = (
    """
    CREATE CONSTRAINT job_application_source_email_id IF NOT EXISTS
    FOR (application:JobApplication)
    REQUIRE application.source_email_id IS UNIQUE
    """,
    """
    CREATE CONSTRAINT company_name IF NOT EXISTS
    FOR (company:Company)
    REQUIRE company.name IS UNIQUE
    """,
    """
    CREATE CONSTRAINT job_role_title IF NOT EXISTS
    FOR (role:JobRole)
    REQUIRE role.title IS UNIQUE
    """,
)

_SAVE_APPLICATION = """
MERGE (application:JobApplication {source_email_id: $source_email_id})
SET application.company = $company,
    application.role = $role,
    application.status = $status,
    application.location = $location,
    application.job_url = $job_url,
    application.applied_at = $applied_at,
    application.email_subject = $email_subject,
    application.email_received_at = $email_received_at,
    application.confidence = $confidence,
    application.notes = $notes
FOREACH (_ IN CASE WHEN $company IS NULL THEN [] ELSE [1] END |
    MERGE (company:Company {name: $company})
    MERGE (company)-[:HAS_APPLICATION]->(application)
)
FOREACH (_ IN CASE WHEN $role IS NULL THEN [] ELSE [1] END |
    MERGE (role:JobRole {title: $role})
    MERGE (application)-[:FOR_ROLE]->(role)
)
"""

_SEARCH_APPLICATIONS = """
MATCH (application:JobApplication)
WHERE ($status IS NULL OR application.status = $status)
  AND ($company IS NULL OR
       toLower(coalesce(application.company, '')) CONTAINS toLower($company))
  AND ($role IS NULL OR
       toLower(coalesce(application.role, '')) CONTAINS toLower($role))
RETURN application.source_email_id AS source_email_id,
       application.company AS company,
       application.role AS role,
       application.status AS status,
       application.location AS location,
       application.job_url AS job_url,
       application.applied_at AS applied_at,
       application.email_subject AS email_subject,
       application.email_received_at AS email_received_at,
       application.confidence AS confidence,
       application.notes AS notes
ORDER BY application.email_received_at DESC
LIMIT $limit
"""

_GET_APPLICATION = """
MATCH (application:JobApplication {source_email_id: $source_email_id})
RETURN application.source_email_id AS source_email_id,
       application.company AS company,
       application.role AS role,
       application.status AS status,
       application.location AS location,
       application.job_url AS job_url,
       application.applied_at AS applied_at,
       application.email_subject AS email_subject,
       application.email_received_at AS email_received_at,
       application.confidence AS confidence,
       application.notes AS notes
"""


class Neo4jGraphStore:
    """Store application email events and query them through fixed Cypher statements."""

    def __init__(self, driver: Any, database: str, read_only: bool = False) -> None:
        self._driver = driver
        self._database = database
        self._read_only = read_only

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def initialize(self) -> None:
        if self._read_only:
            raise PermissionError("A read-only Neo4j store cannot initialize constraints.")

        with self._driver.session(database=self._database) as session:
            for statement in _CREATE_CONSTRAINTS:
                session.run(statement).consume()

    def save(self, application: JobApplication) -> None:
        if self._read_only:
            raise PermissionError("A read-only Neo4j store cannot save applications.")
        if not application.source_email_id:
            raise ValueError("A source Gmail message ID is required for graph storage.")

        properties = application.model_dump(mode="python")
        properties["status"] = application.status.value
        properties["job_url"] = str(application.job_url) if application.job_url else None
        properties["applied_at"] = (
            application.applied_at.isoformat() if application.applied_at else None
        )
        properties["email_received_at"] = (
            application.email_received_at.isoformat() if application.email_received_at else None
        )

        with self._driver.session(database=self._database) as session:
            session.execute_write(self._save_transaction, properties)

    @staticmethod
    def _save_transaction(transaction: Any, properties: dict[str, Any]) -> None:
        transaction.run(_SAVE_APPLICATION, **properties).consume()

    def search_applications(
        self,
        status: ApplicationStatus | None = None,
        company: str | None = None,
        role: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if status is not None and not isinstance(status, ApplicationStatus):
            try:
                status = ApplicationStatus(status)
            except ValueError as error:
                raise ValueError(f"Unsupported application status: {status}") from error

        records = self._read(
            _SEARCH_APPLICATIONS,
            {
                "status": status.value if status else None,
                "company": company.strip() if company and company.strip() else None,
                "role": role.strip() if role and role.strip() else None,
                "limit": limit,
            },
        )
        return records

    def get_application(self, source_email_id: str) -> dict[str, Any] | None:
        if not source_email_id.strip():
            raise ValueError("source_email_id must not be empty.")
        records = self._read(_GET_APPLICATION, {"source_email_id": source_email_id.strip()})
        return records[0] if records else None

    def _read(self, statement: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        with self._driver.session(
            database=self._database,
            default_access_mode=READ_ACCESS,
        ) as session:
            return session.execute_read(
                lambda transaction: [
                    record.data() for record in transaction.run(statement, **parameters)
                ]
            )

    def close(self) -> None:
        self._driver.close()


def build_neo4j_store(settings: Settings, read_only: bool = False) -> Neo4jGraphStore:
    """Create and verify a Neo4j driver with writer or read-only credentials."""

    if not settings.neo4j_uri:
        raise ValueError("NEO4J_URI must be configured.")

    if read_only:
        username = settings.neo4j_mcp_username
        password = settings.neo4j_mcp_password
        if not username or password is None:
            raise ValueError("NEO4J_MCP_USERNAME and NEO4J_MCP_PASSWORD must be configured.")
    else:
        username = settings.neo4j_username
        password = settings.neo4j_password
        if not username or password is None:
            raise ValueError("NEO4J_USERNAME and NEO4J_PASSWORD must be configured.")

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(username, password.get_secret_value()),
    )
    store = Neo4jGraphStore(driver, settings.neo4j_database, read_only=read_only)
    try:
        store.verify_connectivity()
    except Neo4jError:
        store.close()
        raise
    return store
