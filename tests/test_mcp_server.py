import asyncio

from fastmcp import Client

from job_tracker.mcp_server.server import create_mcp_server


class FakeGraphStore:
    def search_applications(self, status=None, company=None, role=None, limit=20):
        return []

    def get_application(self, source_email_id):
        return None


def test_mcp_server_exposes_only_read_only_application_tools():
    server = create_mcp_server(FakeGraphStore())

    async def list_tools():
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(list_tools())

    assert {tool.name for tool in tools} == {"search_applications", "get_application"}
