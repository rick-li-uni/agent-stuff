"""
ADK agent with:
  - Platform tools (user/resource/entitlement APIs — vetted, platform-owned)
  - Skills loaded from DB (contributable, markdown-only, approval-gated)
  - Knowledge search via DB full-text search
  - Skill-creator skill that drafts new contributions and saves to DB
  - Code analyst subagent for discovering knowledge from codebases

Run:
    adk web --port 8000        # from parent dir of adk-poc/
    adk run adk-poc            # CLI mode

Requires:
    DATABASE_URL env var (default: postgresql://skills:skills@localhost:5432/skills)
"""

from __future__ import annotations

import json
import os
import pathlib

from google.adk.agents.llm_agent import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset

from db.repository import ContributionRepository
from agents.code_analyst import code_analyst_agent as _code_analyst


# =============================================================================
# DB REPOSITORY (shared instance)
# =============================================================================

_repo = ContributionRepository()


# =============================================================================
# PLATFORM TOOLS — vetted code, owned by the platform team
# =============================================================================

_USERS = {
    "alice": {"id": "u-001", "email": "alice@corp.com", "name": "Alice"},
    "bob":   {"id": "u-002", "email": "bob@corp.com",   "name": "Bob"},
}

_RESOURCES = {
    "billing-dashboard": {"id": "r-001", "name": "billing-dashboard", "type": "dashboard"},
    "prod-database":     {"id": "r-002", "name": "prod-database",     "type": "database"},
}

_ENTITLEMENTS: list[dict] = []


def get_user(email: str) -> dict:
    """Look up a user by email address.

    Args:
        email: The user's email, e.g. alice@corp.com
    """
    for u in _USERS.values():
        if u["email"] == email:
            return {"status": "found", "user": u}
    return {"status": "not_found", "email": email}


def list_resources(resource_type: str = "") -> dict:
    """List available resources, optionally filtered by type.

    Args:
        resource_type: Filter by type (e.g. "dashboard", "database"). Empty = all.
    """
    results = [
        r for r in _RESOURCES.values()
        if not resource_type or r["type"] == resource_type
    ]
    return {"resources": results, "count": len(results)}


def grant_entitlement(user_id: str, resource_id: str, level: str) -> dict:
    """Grant a user access to a resource at a specific level.

    SAFETY: level="admin" is NEVER auto-approved. The agent must refuse and
    instruct the user to go through the approval workflow.

    Args:
        user_id: The user's ID (e.g. u-001).
        resource_id: The resource's ID (e.g. r-001).
        level: Access level — "read", "write", or "admin".
    """
    if level == "admin":
        return {
            "status": "rejected",
            "reason": "Admin grants require manual approval via the governance portal.",
        }
    ent = {"user_id": user_id, "resource_id": resource_id, "level": level}
    _ENTITLEMENTS.append(ent)
    return {"status": "granted", "entitlement": ent}


def check_entitlement(user_id: str, resource_id: str) -> dict:
    """Check what access level a user has on a resource.

    Args:
        user_id: The user's ID.
        resource_id: The resource's ID.
    """
    for e in _ENTITLEMENTS:
        if e["user_id"] == user_id and e["resource_id"] == resource_id:
            return {"status": "found", "entitlement": e}
    return {"status": "none", "user_id": user_id, "resource_id": resource_id}


def revoke_entitlement(user_id: str, resource_id: str) -> dict:
    """Revoke a user's access to a resource.

    Args:
        user_id: The user's ID.
        resource_id: The resource's ID.
    """
    before = len(_ENTITLEMENTS)
    _ENTITLEMENTS[:] = [
        e for e in _ENTITLEMENTS
        if not (e["user_id"] == user_id and e["resource_id"] == resource_id)
    ]
    removed = before - len(_ENTITLEMENTS)
    return {"status": "revoked" if removed else "not_found", "removed": removed}


# =============================================================================
# TOOL REGISTRY — so skill-creator can validate tool references
# =============================================================================

# Canonical list of platform tools available to skills.
# Skill-creator validates against this; the reference doc mirrors it.
TOOL_REGISTRY = {
    "get_user":            {"category": "platform", "description": "Look up a user by email"},
    "list_resources":      {"category": "platform", "description": "List resources, optionally by type"},
    "grant_entitlement":   {"category": "platform", "description": "Grant a user access to a resource (admin blocked)"},
    "check_entitlement":   {"category": "platform", "description": "Check a user's access level on a resource"},
    "revoke_entitlement":  {"category": "platform", "description": "Revoke a user's access to a resource"},
    "search_knowledge":    {"category": "knowledge", "description": "Full-text search across approved knowledge docs"},
    "list_knowledge":      {"category": "knowledge", "description": "List knowledge docs, filter by domain/tag"},
    "get_knowledge_doc":   {"category": "knowledge", "description": "Retrieve a specific knowledge doc by name"},
    "list_skills_from_db": {"category": "skill",     "description": "List skills from the database"},
    "get_skill_from_db":   {"category": "skill",     "description": "Retrieve a skill's full content by name"},
    "save_contribution":   {"category": "contrib",   "description": "Save a new skill or knowledge draft to DB"},
    "submit_for_review":   {"category": "contrib",   "description": "Submit a draft for approval"},
}


def list_available_tools(category: str = "") -> dict:
    """List all platform tools available for skills to reference.

    Use when creating or validating a skill to check which tool names are valid.

    Args:
        category: Filter by category (platform, knowledge, skill, contrib). Empty = all.
    """
    tools = {
        name: info
        for name, info in TOOL_REGISTRY.items()
        if not category or info["category"] == category
    }
    return {"tools": tools, "count": len(tools)}


# =============================================================================
# KNOWLEDGE & SKILL TOOLS — DB-backed
# =============================================================================

def search_knowledge(query: str) -> dict:
    """Search the knowledge base using full-text search.

    Use when the agent needs to check policies, lessons learned, or reference
    material. Returns approved knowledge docs ranked by relevance.

    Args:
        query: Natural language search query.
    """
    try:
        results = _repo.search(query, type="knowledge")
        return {
            "results": [
                {
                    "id": r.id,
                    "name": r.name,
                    "domain": r.domain,
                    "content": r.content,
                    "tags": r.tags,
                }
                for r in results
            ],
            "count": len(results),
            "query": query,
        }
    except Exception as e:
        return {"error": str(e), "query": query}


def list_knowledge(domain: str = "", tag: str = "") -> dict:
    """List available knowledge docs, optionally filtered.

    Args:
        domain: Filter by domain (e.g. "entitlements"). Empty = all.
        tag: Filter by tag (e.g. "sox"). Empty = all.
    """
    try:
        results = _repo.list_contributions(
            type="knowledge",
            status="approved",
            domain=domain or None,
            tag=tag or None,
        )
        return {
            "entries": [
                {
                    "id": r.id,
                    "name": r.name,
                    "domain": r.domain,
                    "tags": r.tags,
                    "version": r.current_version,
                }
                for r in results
            ],
            "count": len(results),
        }
    except Exception as e:
        return {"error": str(e)}


def get_knowledge_doc(name: str) -> dict:
    """Retrieve a specific knowledge document by name.

    Args:
        name: The knowledge doc name (e.g. "sox-dual-approval").
    """
    try:
        doc = _repo.get_by_name("knowledge", name)
        if not doc:
            return {"status": "not_found", "name": name}
        return {
            "status": "found",
            "id": doc.id,
            "name": doc.name,
            "domain": doc.domain,
            "content": doc.content,
            "tags": doc.tags,
            "version": doc.current_version,
        }
    except Exception as e:
        return {"error": str(e)}


def list_skills_from_db(status: str = "approved") -> dict:
    """List available skills from the database.

    Args:
        status: Filter by status. Default "approved" (only active skills).
    """
    try:
        results = _repo.list_contributions(type="skill", status=status)
        return {
            "entries": [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "version": r.current_version,
                    "description": r.frontmatter.get("description", ""),
                }
                for r in results
            ],
            "count": len(results),
        }
    except Exception as e:
        return {"error": str(e)}


def get_skill_from_db(name: str) -> dict:
    """Retrieve a skill's full content from the database.

    Args:
        name: The skill name (e.g. "access-management").
    """
    try:
        skill = _repo.get_by_name("skill", name)
        if not skill:
            return {"status": "not_found", "name": name}
        return {
            "status": "found",
            "id": skill.id,
            "name": skill.name,
            "content": skill.content,
            "frontmatter": skill.frontmatter,
            "files": skill.files,
            "version": skill.current_version,
            "approval_status": skill.status,
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# CONTRIBUTION TOOLS — for skill-creator to save + submit contributions
# =============================================================================

def save_contribution(
    contribution_type: str,
    name: str,
    content: str,
    author: str,
    domain: str = "",
    description: str = "",
    tags: str = "",
    files: str = "{}",
) -> dict:
    """Save a new skill or knowledge contribution to the database.

    This creates a draft that must be approved before it becomes active.

    Args:
        contribution_type: "skill" or "knowledge".
        name: Kebab-case name for the contribution.
        content: The markdown body content.
        author: Name or team of the person contributing.
        domain: Domain category (for knowledge docs, e.g. "entitlements").
        description: Short description (for skills, goes in frontmatter).
        tags: Comma-separated tags (e.g. "sox,compliance").
        files: JSON string of additional files (e.g. '{"evals/test.yaml": "content"}').
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    frontmatter = {}
    if description:
        frontmatter["description"] = description
    if contribution_type == "skill":
        frontmatter["name"] = name

    try:
        parsed_files = json.loads(files) if files and files != "{}" else {}
    except json.JSONDecodeError:
        parsed_files = {}

    # check for code files
    for fpath in parsed_files:
        ext = pathlib.Path(fpath).suffix.lower()
        if ext not in {".md", ".yaml", ".yml", ".json", ".csv"}:
            return {"status": "rejected", "reason": f"File '{fpath}' has disallowed extension '{ext}'."}

    try:
        existing = _repo.get_by_name(contribution_type, name)
        if existing:
            c = _repo.update_content(
                existing.id,
                content=content,
                updated_by=author,
                frontmatter=frontmatter,
                files=parsed_files,
                change_summary=f"Updated by {author}",
            )
            return {
                "status": "updated",
                "id": c.id,
                "name": c.name,
                "version": c.current_version,
                "approval_status": c.status,
            }
        else:
            c = _repo.create(
                type=contribution_type,
                name=name,
                content=content,
                created_by=author,
                domain=domain or None,
                frontmatter=frontmatter,
                files=parsed_files,
                tags=tag_list,
            )
            return {
                "status": "created",
                "id": c.id,
                "name": c.name,
                "version": 1,
                "approval_status": c.status,
            }
    except Exception as e:
        return {"error": str(e)}


def submit_for_review(contribution_id: int) -> dict:
    """Submit a draft contribution for review and approval.

    Args:
        contribution_id: The contribution's database ID.
    """
    try:
        c = _repo.submit_for_review(contribution_id)
        return {
            "status": "submitted",
            "id": c.id,
            "name": c.name,
            "approval_status": c.status,
        }
    except Exception as e:
        return {"error": str(e)}


def get_contribution_history(contribution_id: int) -> dict:
    """Get the version and approval history for a contribution.

    Args:
        contribution_id: The contribution's database ID.
    """
    try:
        history = _repo.get_version_history(contribution_id)
        return {"contribution_id": contribution_id, "versions": history}
    except Exception as e:
        return {"error": str(e)}


def list_pending_reviews() -> dict:
    """List all contributions awaiting approval.

    Use when an approver wants to see what needs review.
    """
    try:
        results = _repo.list_contributions(status="pending_review")
        return {
            "pending": [
                {
                    "id": r.id,
                    "type": r.type,
                    "name": r.name,
                    "domain": r.domain,
                    "version": r.current_version,
                    "created_by": r.created_by,
                    "content_preview": (r.content or "")[:200],
                }
                for r in results
            ],
            "count": len(results),
        }
    except Exception as e:
        return {"error": str(e)}


def approve_contribution(contribution_id: int, approver: str, reason: str = "") -> dict:
    """Approve a pending contribution, making it active.

    Only contributions in 'pending_review' status can be approved.
    The approver MUST be different from the author (separation of duties).

    Args:
        contribution_id: The contribution's database ID.
        approver: Name of the person approving.
        reason: Optional reason for the approval.
    """
    try:
        c = _repo.get_by_id(contribution_id)
        if not c:
            return {"error": f"Contribution {contribution_id} not found"}
        if c.status != "pending_review":
            return {"error": f"Contribution is '{c.status}', not 'pending_review'"}
        if c.created_by == approver:
            return {"error": "Author cannot approve their own contribution (separation of duties)."}

        a = _repo.approve(contribution_id, c.current_version, approver, reason)
        return {
            "status": "approved",
            "id": contribution_id,
            "name": c.name,
            "version": c.current_version,
            "approved_by": approver,
        }
    except Exception as e:
        return {"error": str(e)}


def reject_contribution(contribution_id: int, approver: str, reason: str) -> dict:
    """Reject a pending contribution with a reason.

    Args:
        contribution_id: The contribution's database ID.
        approver: Name of the person rejecting.
        reason: Why the contribution is being rejected (required).
    """
    try:
        c = _repo.get_by_id(contribution_id)
        if not c:
            return {"error": f"Contribution {contribution_id} not found"}
        if c.status != "pending_review":
            return {"error": f"Contribution is '{c.status}', not 'pending_review'"}

        _repo.reject(contribution_id, c.current_version, approver, reason)
        return {
            "status": "rejected",
            "id": contribution_id,
            "name": c.name,
            "rejected_by": approver,
            "reason": reason,
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# OPPORTUNISTIC LEARNING — capture knowledge mid-session
# =============================================================================

def capture_learning(
    fact: str,
    domain: str,
    source: str,
    existing_doc: str = "",
) -> dict:
    """Capture a fact learned during a session — create or update a knowledge doc.

    Use this IMMEDIATELY when you learn something new mid-session:
    - The user corrects you or provides new information
    - You discover a tool behaves differently than documented
    - You find existing knowledge is outdated or wrong
    - The user mentions a policy, constraint, or fact not in the KB

    This is lighter than save_contribution — use it for quick mid-session
    captures. The fact is saved as a draft and submitted for review.

    Args:
        fact: The fact or rule to capture, written for the agent (actionable).
        domain: Domain category (e.g. "entitlements", "onboarding").
        source: How you learned this (e.g. "user corrected me", "discovered via get_user").
        existing_doc: If this updates an existing knowledge doc, its name. Empty = new doc.
    """
    import re
    name = existing_doc or re.sub(r'[^a-z0-9]+', '-', fact[:60].lower()).strip('-')

    content = f"""{fact}

_Source: {source}_
"""
    frontmatter = {
        "title": fact[:120],
        "domain": domain,
        "source": source,
        "captured_by": "opportunistic-learning",
    }

    try:
        if existing_doc:
            existing = _repo.get_by_name("knowledge", existing_doc)
            if existing:
                updated_content = existing.content + f"\n\n---\n\n**Update:** {fact}\n\n_Source: {source}_"
                c = _repo.update_content(
                    existing.id,
                    content=updated_content,
                    updated_by="opportunistic-learning",
                    change_summary=f"Added: {fact[:80]}",
                )
                return {
                    "status": "updated_existing",
                    "id": c.id,
                    "name": existing_doc,
                    "version": c.current_version,
                    "approval_status": c.status,
                }

        c = _repo.create(
            type="knowledge",
            name=name,
            content=content,
            created_by="opportunistic-learning",
            domain=domain,
            frontmatter=frontmatter,
            tags=["auto-captured"],
        )
        _repo.submit_for_review(c.id)
        return {
            "status": "captured_and_submitted",
            "id": c.id,
            "name": name,
            "approval_status": "pending_review",
        }
    except Exception as e:
        return {"error": str(e)}


def flag_stale_knowledge(doc_name: str, what_is_wrong: str, correct_info: str) -> dict:
    """Flag an existing knowledge doc as stale or incorrect.

    Use when you discover during a session that a knowledge doc gave you wrong
    or outdated information. This creates a correction proposal.

    Args:
        doc_name: Name of the knowledge doc that is stale/wrong.
        what_is_wrong: What specifically is incorrect or outdated.
        correct_info: The correct information (if known).
    """
    correction = f"""# Correction: {doc_name}

**What is wrong:** {what_is_wrong}

**Correct information:** {correct_info}

_Flagged during a live session by the agent._
"""
    try:
        c = _repo.create(
            type="knowledge",
            name=f"correction-{doc_name}",
            content=correction,
            created_by="opportunistic-learning",
            domain="corrections",
            frontmatter={
                "corrects": doc_name,
                "what_is_wrong": what_is_wrong,
            },
            tags=["correction", "auto-flagged"],
        )
        _repo.submit_for_review(c.id)
        return {
            "status": "flagged",
            "id": c.id,
            "corrects": doc_name,
            "approval_status": "pending_review",
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# SESSION RETROSPECTIVE — post-task self-improvement loop
# =============================================================================

def session_retrospective(
    task_summary: str,
    skill_used: str = "",
    what_went_well: str = "",
    what_was_missing: str = "",
    suggestions: str = "[]",
) -> dict:
    """Analyze the session and propose skill/knowledge/eval improvements.

    Call this AFTER completing every task. Review what happened and propose
    concrete improvements as structured suggestions.

    Args:
        task_summary: One-line summary of what the user asked and what you did.
        skill_used: Which skill guided the task (empty if none).
        what_went_well: What worked — confirm existing skills/knowledge were helpful.
        what_was_missing: What was missing, wrong, or could be better.
        suggestions: JSON array of improvement proposals. Each item:
            {
                "type": "skill_update" | "knowledge_add" | "knowledge_update" | "eval_add",
                "target": "skill or knowledge name",
                "description": "what to change and why",
                "priority": "high" | "medium" | "low",
                "draft_content": "optional — drafted markdown if ready"
            }
    """
    try:
        parsed = json.loads(suggestions) if suggestions and suggestions != "[]" else []
    except json.JSONDecodeError:
        parsed = []

    saved_ids = []
    for s in parsed:
        if not s.get("description"):
            continue

        if s["type"] in ("knowledge_add", "knowledge_update") and s.get("draft_content"):
            result = save_contribution(
                contribution_type="knowledge",
                name=s.get("target", "auto-" + s["type"]),
                content=s["draft_content"],
                author="session-retrospective",
                description=s["description"],
                tags=f"auto-suggested,{s.get('priority', 'medium')}",
            )
            if result.get("id"):
                submit_for_review(result["id"])
                saved_ids.append({"id": result["id"], "type": s["type"], "name": s.get("target")})

    return {
        "status": "retrospective_recorded",
        "task_summary": task_summary,
        "skill_used": skill_used,
        "suggestions_count": len(parsed),
        "auto_submitted": saved_ids,
        "suggestions": parsed,
    }


# =============================================================================
# SKILLS — loaded from filesystem (the skill-creator skill itself)
# The skill-creator is a "bootstrap" skill — it lives on disk because it
# teaches the agent how to use the DB. Other skills are loaded from DB.
# =============================================================================

_SKILLS_DIR = pathlib.Path(__file__).parent / "skills"
_loaded_skills = []

# Only load skill-creator from filesystem (the meta-skill)
_skill_creator_dir = _SKILLS_DIR / "skill-creator"
if _skill_creator_dir.exists() and (_skill_creator_dir / "SKILL.md").exists():
    try:
        _loaded_skills.append(load_skill_from_dir(_skill_creator_dir))
    except Exception as e:
        print(f"Warning: failed to load skill-creator: {e}")

_skill_toolset = skill_toolset.SkillToolset(skills=_loaded_skills) if _loaded_skills else None


# =============================================================================
# ROOT AGENT
# =============================================================================

_tools: list = [
    # Platform tools (API wrappers)
    get_user,
    list_resources,
    grant_entitlement,
    check_entitlement,
    revoke_entitlement,
    # Tool registry
    list_available_tools,
    # Knowledge tools (DB-backed)
    search_knowledge,
    list_knowledge,
    get_knowledge_doc,
    # Skill tools (DB-backed)
    list_skills_from_db,
    get_skill_from_db,
    # Contribution tools (for skill-creator)
    save_contribution,
    submit_for_review,
    get_contribution_history,
    # Approval tools (for reviewers)
    list_pending_reviews,
    approve_contribution,
    reject_contribution,
    # Opportunistic learning
    capture_learning,
    flag_stale_knowledge,
    # Retrospective
    session_retrospective,
]
if _skill_toolset:
    _tools.append(_skill_toolset)

root_agent = Agent(
    model="gemini-2.5-flash",
    name="platform_agent",
    description="Platform agent with access management tools, DB-backed skills and knowledge.",
    instruction="""\
You are a platform operations agent. You help with:

1. **Access management** — look up users, resources, and entitlements; grant or
   revoke access. NEVER grant admin access without directing the user to the
   approval workflow. Before granting access, search the knowledge base for any
   relevant policies (e.g. SOX requirements).

2. **Knowledge lookup** — when a user asks about policies, procedures, or
   "how does X work", search the knowledge base first using search_knowledge.
   If you find relevant docs, use them to inform your answer.

3. **Skill creation** — when an ops user wants to create a new skill or
   knowledge contribution, use the skill-creator skill to interview them,
   draft the content, then use save_contribution to store it in the database
   and submit_for_review to send it for approval.

4. **Browsing** — use list_skills_from_db, list_knowledge, get_skill_from_db,
   and get_knowledge_doc to help users explore what's available.

Always confirm destructive actions (revoke) before executing.
When creating contributions, validate against the house rules in the
skill-creator skill before saving.

Contributions are saved as drafts and must be approved before they become
active. Always call submit_for_review after saving a new contribution.

5. **Opportunistic learning** — capture knowledge THE MOMENT you learn it,
   don't wait for the retrospective. Use capture_learning or flag_stale_knowledge
   DURING the session when any of these happen:

   **User corrects you:**
   User: "Actually, billing-dashboard is owned by the Finance team, not Ops."
   → Immediately: capture_learning(
       fact="billing-dashboard is owned by the Finance team",
       domain="resources",
       source="user corrected agent assumption")
   → Then continue the task. Don't stop to discuss the capture.

   **User provides new info unprompted:**
   User: "By the way, we just added a PCI compliance tier last week."
   → Immediately: capture_learning(
       fact="Resources can have a PCI compliance tier (in addition to SOX)",
       domain="resources",
       source="user mentioned during session")

   **You discover a tool behaves differently than documented:**
   grant_entitlement returns an unexpected field or error
   → Immediately: flag_stale_knowledge(
       doc_name="entitlements",
       what_is_wrong="grant_entitlement returns X but docs say Y",
       correct_info="The actual behavior is...")

   **Knowledge search returns something that contradicts what the user says:**
   KB says single approval, user says dual approval is the new policy
   → Immediately: flag_stale_knowledge(...)

   The key behavior: **capture first, continue the task, don't ask the user
   "should I save this?"** The capture goes to review — if it's wrong, the
   reviewer rejects it. Bias toward capturing. A rejected draft costs nothing;
   a lost insight costs a future mistake.

6. **Post-task retrospective** — after EVERY completed task, call
   session_retrospective to analyze what happened and propose improvements.
   Ask yourself these questions:

   **Skill gaps:**
   - Did the skill's workflow match what I actually had to do, or did I
     improvise steps? → propose a skill_update
   - Was there a task I handled without any skill guiding me? → propose
     a new skill

   **Knowledge gaps:**
   - Did I encounter a fact, policy, or constraint that wasn't in the
     knowledge base? (e.g. the user told me something I should have
     already known) → propose knowledge_add
   - Was any knowledge doc outdated or wrong? → propose knowledge_update

   **Eval gaps:**
   - Did the user's request represent an edge case not covered by existing
     evals? → propose eval_add
   - Did I almost make a mistake that an eval should catch? → propose a
     safety eval_add

   For knowledge suggestions with clear content, include draft_content so
   the proposal is ready for review. For skill updates and evals, describe
   what should change — the skill-creator bot handles the actual drafting.

   Keep the retrospective brief. Only propose improvements that would
   genuinely help future sessions — don't propose for the sake of proposing.

6. **Code analysis** — when asked to analyze a codebase, discover API patterns,
   or extract knowledge from a repo, delegate to the code_analyst subagent.
   Say: "I'll hand this off to the code analyst." The subagent will clone the
   repo, analyze it, and propose knowledge docs through the same approval pipeline.
""",
    tools=_tools,
    sub_agents=[_code_analyst],
)
