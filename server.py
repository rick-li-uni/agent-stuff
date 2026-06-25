"""
A minimal MCP (Model Context Protocol) server.

It exposes a tiny in-memory "notes" knowledge base to any MCP-aware AI agent
(Claude Desktop, Claude Code, the Anthropic SDK, etc.) through the three core
MCP primitives:

  - Tools     : actions the model can CALL          (add_note, search_notes, get_weather)
  - Resources : data the model can READ by URI       (notes://all)
  - Prompts   : reusable prompt templates the UI can surface (summarize_notes)

Run it:
    python server.py            # speaks MCP over stdio (how desktop apps launch it)

The transport is stdio: the host process starts this script and talks JSON-RPC
over stdin/stdout. You never open a port. That is one of the structural
differences from REST (see README.md).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

# The server's name is part of its identity in the MCP handshake.
mcp = FastMCP("notes-demo")

# A toy datastore so the example is self-contained. In a real server this would
# be a database, an internal API, the filesystem, etc.
_NOTES: list[str] = [
    "MCP standardizes how models discover and call tools.",
    "REST endpoints are designed for human-written client code.",
]


# ---- Tools: things the model can DO -----------------------------------------
# The docstring and type hints ARE the contract. FastMCP turns them into a JSON
# schema the model sees, so the model knows when and how to call this — no
# separate API docs, no hand-written tool definitions.

@mcp.tool()
def add_note(text: str) -> str:
    """Save a note to the knowledge base.

    Args:
        text: The note content to store.
    """
    _NOTES.append(text)
    return f"Saved. The knowledge base now has {len(_NOTES)} notes."


@mcp.tool()
def search_notes(query: str) -> list[str]:
    """Search saved notes for a case-insensitive substring match.

    Args:
        query: Text to look for inside the notes.
    """
    q = query.lower()
    return [n for n in _NOTES if q in n.lower()]


@mcp.tool()
def get_weather(city: str) -> str:
    """Get the (pretend) current weather for a city.

    Args:
        city: City name, e.g. "Paris".
    """
    # Stubbed — a real server would call a weather API here.
    return f"It's 72°F and sunny in {city}."


# ---- Resource: data the model can READ --------------------------------------
# Resources are addressed by URI and are read-only context, not actions.

@mcp.resource("notes://all")
def all_notes() -> str:
    """Return every saved note as a newline-delimited list."""
    return "\n".join(f"- {n}" for n in _NOTES)


# ---- Prompt: a reusable template the host UI can offer the user --------------

@mcp.prompt()
def summarize_notes() -> str:
    """A ready-made prompt that asks the model to summarize all notes."""
    return "Read the notes://all resource and summarize the key themes in 3 bullets."


if __name__ == "__main__":
    mcp.run()  # defaults to stdio transport
