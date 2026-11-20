"""Read-only FastMCP tools for searching job applications in Neo4j."""

from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from job_tracker.config import get_settings
from job_tracker.integrations.neo4j_store import Neo4jGraphStore, build_neo4j_store
from job_tracker.models import ApplicationStatus


def create_mcp_server(store: Neo4jGraphStore) -> FastMCP:
    """Create the local stdio MCP server with bounded, read-only tools."""

    mcp = FastMCP(
        name="job-application-tracker",
        instructions="Search and inspect job application records. All tools are read-only.",
    )

    @mcp.tool(
        description="Search applications by status, company, or role.",
        annotations={"readOnlyHint": True, "openWorldHint": False},
    )
    def search_applications(
        status: ApplicationStatus | None = None,
        company: str | None = None,
        role: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> list[dict[str, Any]]:
        return store.search_applications(status, company, role, limit)

    @mcp.tool(
        description="Get one application by its source Gmail message ID.",
        annotations={"readOnlyHint": True, "openWorldHint": False},
    )
    def get_application(source_email_id: str) -> dict[str, Any] | None:
        return store.get_application(source_email_id)

    return mcp


def main() -> None:
    settings = get_settings()
    store = build_neo4j_store(settings, read_only=True)
    try:
        create_mcp_server(store).run(transport="stdio")
    finally:
        store.close()


if __name__ == "__main__":
    main()
