"""
Smoke test: launch server.py as an MCP subprocess, then act as the *host* —
list what it exposes and call a tool. This is exactly the choreography an AI
agent's runtime does for you; here we do it by hand to make it visible.
"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    # Launch the server with the same interpreter running this client.
    params = StdioServerParameters(command=sys.executable, args=["server.py"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # the MCP handshake

            # 1. Discovery — the agent learns the toolset at runtime, no docs needed.
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            resources = await session.list_resources()
            print("RESOURCES:", [str(r.uri) for r in resources.resources])

            # 2. Call a tool by name with structured args.
            result = await session.call_tool("add_note", {"text": "MCP is transport-agnostic."})
            print("add_note ->", result.content[0].text)

            found = await session.call_tool("search_notes", {"query": "REST"})
            print("search_notes ->", [c.text for c in found.content])

            # 3. Read a resource by URI.
            doc = await session.read_resource("notes://all")
            print("notes://all ->\n" + doc.contents[0].text)


if __name__ == "__main__":
    asyncio.run(main())
