import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_initialize_list_and_call_with_missing_token():
    asyncio.run(_stdio_roundtrip())


async def _stdio_roundtrip():
    env = dict(os.environ)
    env.pop("CAMINO_API_TOKEN", None)
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "camino_mcp.server"], env=env
    )
    async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
        initialized = await session.initialize()
        assert initialized.serverInfo.name == "Camino"
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"list_courses", "list_assignments", "upcoming", "overdue", "grades"} <= names
        invalid = await session.call_tool("list_assignments", {"course_id": "../42"})
        assert invalid.isError or "course_id" in str(invalid)
        missing = await session.call_tool("list_courses", {})
        assert "CAMINO_API_TOKEN is not set" in str(missing)
        assert not missing.isError
