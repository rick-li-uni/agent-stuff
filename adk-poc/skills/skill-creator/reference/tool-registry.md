# Available Platform Tools

These are the shared tools available to all skills. When creating a skill,
only reference tools from this list. Use `list_available_tools()` to verify
at runtime.

## Platform tools (API wrappers)

| Tool | Description | Key args |
|---|---|---|
| `get_user` | Look up a user by email | `email` |
| `list_resources` | List resources, optionally by type | `resource_type` (optional) |
| `grant_entitlement` | Grant a user access to a resource. **Admin level auto-rejected.** | `user_id`, `resource_id`, `level` |
| `check_entitlement` | Check a user's access level on a resource | `user_id`, `resource_id` |
| `revoke_entitlement` | Revoke a user's access | `user_id`, `resource_id` |

## Knowledge tools

| Tool | Description | Key args |
|---|---|---|
| `search_knowledge` | Full-text search across approved knowledge docs | `query` |
| `list_knowledge` | List knowledge docs, filter by domain/tag | `domain`, `tag` (both optional) |
| `get_knowledge_doc` | Retrieve a specific knowledge doc by name | `name` |

## Skill tools

| Tool | Description | Key args |
|---|---|---|
| `list_skills_from_db` | List skills from the database | `status` (default "approved") |
| `get_skill_from_db` | Retrieve a skill's full content | `name` |

## Contribution tools (used by skill-creator internally)

| Tool | Description | Key args |
|---|---|---|
| `save_contribution` | Save a new skill or knowledge draft | `contribution_type`, `name`, `content`, `author`, ... |
| `submit_for_review` | Submit a draft for approval | `contribution_id` |
| `get_contribution_history` | Get version + approval history | `contribution_id` |
| `list_available_tools` | List this registry (for validation) | `category` (optional) |

## Approval tools (reviewer-only)

| Tool | Description | Key args |
|---|---|---|
| `list_pending_reviews` | List contributions awaiting approval | — |
| `approve_contribution` | Approve a pending contribution | `contribution_id`, `approver` |
| `reject_contribution` | Reject with reason | `contribution_id`, `approver`, `reason` |

## Rules for referencing tools in skills

1. **Only reference tools that exist in this registry.** Call
   `list_available_tools()` to verify if unsure.
2. **Use the exact tool name** — `get_user`, not `getUser` or `lookup_user`.
3. **Platform tools are shared** — you don't define them in the skill, you
   reference them by name in workflows and eval cases.
4. **If a tool is missing**, the skill author cannot add it — tools are
   platform-owned code. Flag it as a request to the platform team.
