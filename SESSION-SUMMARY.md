# Agent Skills & Knowledge Architecture — Session Summary

## What we built

### 1. MCP Server (`server.py`)
A working MCP server demonstrating the protocol: 3 tools, 1 resource, 1 prompt.
Runs over stdio. `check.py` is the smoke-test client. Verified working.

### 2. ADK PoC (`adk-poc/`)
A Google ADK agent with the full enterprise architecture:

**Platform tools (code, vetted, platform-owned):**
- `get_user`, `list_resources`, `grant_entitlement`, `check_entitlement`, `revoke_entitlement`
- `search_knowledge`, `list_knowledge`
- `write_contribution_file`, `open_skill_pr`

**Skills (markdown, contributable by ops):**
- `skill-creator` — interviews ops users, drafts skills OR knowledge docs, validates against house rules, opens a PR via git CLI
- `access-management` — workflows for user/resource/entitlement management

**Knowledge (markdown, contributable by ops via skill-creator):**
- `knowledge/` dir with `manifest.yaml` + domain folders
- Sample: `entitlements/sox-dual-approval.md`

## Key architecture decisions

### Two-layer separation
| Layer | Contains | Who owns | Contains code? |
|---|---|---|---|
| Tools | executable capabilities | platform team | yes |
| Skills + Knowledge | instructions + facts | ops-contributable | NO — markdown only |

### Release control for contributions
- Skill-creator bot drafts + opens PR via git CLI (`gh pr create`)
- CI validates: no-code check, frontmatter, eval suites
- Branch protection: requires CI pass + human approval
- Bot can create PRs but CANNOT merge (least-privilege service account)
- Author ≠ approver (separation of duties preserved)

### Skills vs Knowledge
| | Skills | Knowledge |
|---|---|---|
| Purpose | HOW — workflows, rules | WHAT — facts, policies, lessons |
| Structure | `SKILL.md` + frontmatter + evals | doc with YAML frontmatter |
| Lifecycle | PR-gated, eval-tested | PR-gated, manifest-tracked |
| Runtime | loaded by agent on trigger | searched via `search_knowledge` tool |

### When to add a vector DB
- Current: filesystem + keyword search (fine for <50 docs)
- Add vector DB when: corpus > 50 docs, need semantic search, model can't pick the right file by name

### MCP vs REST for agents
- MCP: discovery built in, one protocol for all tools, action vs data explicit, transport-agnostic
- REST: still right for public APIs, high-throughput service-to-service, single-endpoint integrations
- Common pattern: keep REST API, wrap in thin MCP server

### Automated testing (3 eval suites per PR)
1. **Functional** — contributor's own cases (happy + edge + safety)
2. **Trigger/routing** — skill activates when it should, doesn't hijack unrelated prompts
3. **Safety/regression** — full suite + adversarial prompts

### Dynamic code generation stance
- Generation is upstream of the gate, never a bypass
- Model can draft; model cannot approve or deploy
- Immutable versions, version pinning, environment promotion

## How to run

```bash
# MCP server smoke test
cd /Users/kl68884/projects/genai/agent-stuff
.venv/bin/python check.py

# ADK agent
# Set GOOGLE_API_KEY in adk-poc/.env first
.venv/bin/adk web --port 8000
# or: .venv/bin/adk run adk-poc
```

## Key references
- Anthropic skills repo: https://github.com/anthropics/skills
- skill-creator skill: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- ADK skills docs: https://adk.dev/skills/
- Agent Skills spec: https://agentskills.io/specification
