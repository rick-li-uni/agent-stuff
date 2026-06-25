# A simple MCP server — and why agents prefer it over REST

This folder contains a tiny, runnable MCP server (`server.py`) and a smoke-test
client (`check.py`) that exercises it. Below is the "why."

## Run it

```bash
python3.12 -m venv .venv
./.venv/bin/pip install mcp
./.venv/bin/python check.py        # acts as the host: lists + calls the server
```

To use it from a real agent (Claude Desktop), add this to
`~/Library/Application Support/Claude/claude_desktop_config.json` (see
`claude_desktop_config.example.json`) and restart the app — the tools then
appear to Claude automatically.

## What MCP is

MCP (Model Context Protocol) is an open standard for connecting AI agents to
tools and data. A **host** (Claude Desktop, Claude Code, your own agent loop)
launches one or more **servers**; each server advertises three kinds of
capabilities:

| Primitive   | The model can… | In `server.py`            |
|-------------|----------------|---------------------------|
| **Tool**    | *call* it      | `add_note`, `search_notes`, `get_weather` |
| **Resource**| *read* it      | `notes://all`             |
| **Prompt**  | *be offered* it| `summarize_notes`         |

The model discovers all of this at runtime via the handshake — there is no
out-of-band documentation it has to be told about.

## MCP vs REST for an AI agent

You *can* give an agent a REST API. The difference is who does the integration
work and when.

### 1. Discovery is built in
- **REST:** the agent only knows an endpoint exists if *you* hand-write a tool
  definition describing it (name, JSON schema, when to use it). Add an endpoint →
  you edit the agent's tool list.
- **MCP:** the server answers `list_tools` / `list_resources` itself. The
  docstring + type hints in `server.py` *become* the schema the model sees. Add a
  `@mcp.tool()` → every connected agent can use it immediately, no agent-side change.

### 2. One protocol vs N bespoke integrations
- **REST:** every API has its own auth, pagination, error shapes, and base URL.
  Wiring 10 services into an agent is 10 custom adapters.
- **MCP:** every server speaks the same JSON-RPC verbs (`list_tools`,
  `call_tool`, `read_resource`). The agent learns the protocol once; any server
  plugs in. This is the "USB-C for AI tools" pitch.

### 3. Action vs data is explicit
- **REST:** `GET /notes` and `POST /notes` are both just HTTP. The agent's
  harness can't tell read-only from state-changing without you encoding that.
- **MCP:** **resources** are read-only context; **tools** are actions. Hosts use
  that split for UX and safety — e.g. auto-loading a resource but prompting the
  user before a tool with side effects runs.

### 4. Transport-agnostic, capability-oriented
- **REST:** coupled to HTTP and a running, reachable server.
- **MCP:** the same server works over **stdio** (a local subprocess — what
  `check.py` and Claude Desktop use; no port, no network) or over HTTP/SSE for
  remote servers. The agent code is identical either way.

### When REST is still the right call
- A public, browser-facing, or non-agent API.
- High-throughput service-to-service traffic where you don't want a model in the loop.
- You already have REST and just need *one* agent to hit *one* endpoint — wrapping
  it in MCP is overkill.

Common pattern: keep your REST API, and write a thin MCP server that calls it.
That's exactly what `get_weather` models — a stub today, a `requests.get(...)`
to a real weather API tomorrow. The agent never knows the difference.

## The one-line summary

REST is an interface designed for *programmers* to write client code against.
MCP is an interface designed for *models* to discover and drive at runtime — so
adding a capability is a server-side change, not an agent-side one.
