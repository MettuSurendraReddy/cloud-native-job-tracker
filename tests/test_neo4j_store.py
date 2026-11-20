import pytest
from neo4j import READ_ACCESS

from job_tracker.integrations.neo4j_store import Neo4jGraphStore
from job_tracker.models import ApplicationStatus, JobApplication


class FakeResult:
    def __init__(self, records=None):
        self.records = [FakeRecord(record) for record in records or []]
        self.consumed = False

    def consume(self):
        self.consumed = True

    def __iter__(self):
        return iter(self.records)


class FakeRecord:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeTransaction:
    def __init__(self, records=None):
        self.records = records or []
        self.calls = []

    def run(self, statement, **parameters):
        self.calls.append((statement, parameters))
        return FakeResult(self.records)


class FakeSession:
    def __init__(self, transaction):
        self.transaction = transaction
        self.access_mode = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def run(self, statement):
        return self.transaction.run(statement)

    def execute_write(self, callback, parameters):
        return callback(self.transaction, parameters)

    def execute_read(self, callback):
        return callback(self.transaction)


class FakeDriver:
    def __init__(self, records=None):
        self.transaction = FakeTransaction(records)
        self.sessions = []
        self.closed = False

    def session(self, database, default_access_mode=None):
        session = FakeSession(self.transaction)
        session.access_mode = default_access_mode
        self.sessions.append(session)
        return session

    def verify_connectivity(self):
        return None

    def close(self):
        self.closed = True


def test_initialize_creates_unique_constraints():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver, "neo4j")

    store.initialize()

    assert len(driver.transaction.calls) == 3
    assert all("IF NOT EXISTS" in query for query, _ in driver.transaction.calls)


def test_save_merges_application_and_relationships_by_email_id():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver, "neo4j")
    application = JobApplication(
        source_email_id="gmail-123",
        company="Example Corp",
        role="Engineer",
        status=ApplicationStatus.OFFER,
    )

    store.save(application)

    query, parameters = driver.transaction.calls[0]
    assert "MERGE (application:JobApplication" in query
    assert "HAS_APPLICATION" in query
    assert "FOR_ROLE" in query
    assert parameters["source_email_id"] == "gmail-123"
    assert parameters["status"] == "offer"


def test_search_uses_read_access_and_bound_parameters():
    record = {"source_email_id": "gmail-123", "status": "interview"}
    driver = FakeDriver(records=[record])
    store = Neo4jGraphStore(driver, "neo4j", read_only=True)

    applications = store.search_applications(
        status=ApplicationStatus.INTERVIEW,
        company=" Example Corp ",
        limit=10,
    )

    assert applications == [record]
    assert driver.sessions[0].access_mode == READ_ACCESS
    query, parameters = driver.transaction.calls[0]
    assert "$company" in query
    assert parameters["company"] == "Example Corp"
    assert parameters["status"] == "interview"


def test_read_only_store_rejects_writes():
    store = Neo4jGraphStore(FakeDriver(), "neo4j", read_only=True)

    with pytest.raises(PermissionError, match="read-only"):
        store.save(
            JobApplication(
                source_email_id="gmail-123",
                company="Example Corp",
                role="Engineer",
                status=ApplicationStatus.APPLIED,
            )
        )


@pytest.mark.parametrize("limit", [0, 101])
def test_search_rejects_unbounded_limits(limit):
    store = Neo4jGraphStore(FakeDriver(), "neo4j", read_only=True)

    with pytest.raises(ValueError, match="between 1 and 100"):
        store.search_applications(limit=limit)


def test_search_rejects_unknown_status():
    store = Neo4jGraphStore(FakeDriver(), "neo4j", read_only=True)

    with pytest.raises(ValueError, match="Unsupported application status"):
        store.search_applications(status="unknown-status")
