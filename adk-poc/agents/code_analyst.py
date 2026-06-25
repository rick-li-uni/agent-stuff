"""
Code Analyst subagent — clones repos, discovers knowledge and skill gaps,
proposes contributions through the same approval pipeline.

Delegated to by the root agent when a user asks to analyze a codebase.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Optional

from google.adk.agents.llm_agent import Agent


# =============================================================================
# TOOLS — repo access + code analysis (platform-owned, vetted)
# =============================================================================

WORK_DIR = pathlib.Path(os.environ.get("CODE_ANALYST_WORKDIR", "/tmp/code-analyst"))


def clone_repo(repo_url: str, branch: str = "") -> dict:
    """Clone a git repository for analysis.

    Args:
        repo_url: HTTPS URL of the git repo.
        branch: Branch to clone (default: repo's default branch).
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    target = WORK_DIR / repo_name

    if target.exists():
        shutil.rmtree(target)

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "clone", "--depth", "50"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo_url, str(target)]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        return {"status": "error", "error": result.stderr.strip()}

    return {"status": "cloned", "path": str(target), "repo": repo_name}


def list_repo_files(repo_name: str, path: str = "", pattern: str = "") -> dict:
    """List files in a cloned repo, optionally filtered by glob pattern.

    Args:
        repo_name: Name of the cloned repo.
        path: Subdirectory to list (relative to repo root). Empty = root.
        pattern: Glob pattern to filter (e.g. "*.py", "**/*.md"). Empty = all.
    """
    repo_path = WORK_DIR / repo_name / path
    if not repo_path.exists():
        return {"status": "not_found", "path": str(repo_path)}

    resolved = repo_path.resolve()
    if not str(resolved).startswith(str((WORK_DIR / repo_name).resolve())):
        return {"status": "error", "error": "Path escapes repo directory"}

    if pattern:
        files = [str(f.relative_to(WORK_DIR / repo_name)) for f in repo_path.rglob(pattern) if f.is_file()]
    else:
        files = [str(f.relative_to(WORK_DIR / repo_name)) for f in repo_path.rglob("*") if f.is_file()]

    files = files[:200]
    return {"files": files, "count": len(files), "truncated": len(files) >= 200}


def read_repo_file(repo_name: str, file_path: str) -> dict:
    """Read a file from a cloned repo.

    Args:
        repo_name: Name of the cloned repo.
        file_path: Path relative to repo root.
    """
    target = WORK_DIR / repo_name / file_path
    resolved = target.resolve()
    if not str(resolved).startswith(str((WORK_DIR / repo_name).resolve())):
        return {"status": "error", "error": "Path escapes repo directory"}

    if not target.exists():
        return {"status": "not_found", "file": file_path}

    if target.stat().st_size > 100_000:
        return {"status": "too_large", "size": target.stat().st_size, "file": file_path}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "error", "error": str(e)}

    return {"status": "ok", "file": file_path, "content": content, "lines": content.count("\n") + 1}


def search_repo(repo_name: str, query: str, file_pattern: str = "") -> dict:
    """Search a cloned repo for a text pattern using grep.

    Args:
        repo_name: Name of the cloned repo.
        query: Text or regex pattern to search for.
        file_pattern: Limit search to files matching this glob (e.g. "*.py"). Empty = all.
    """
    repo_path = WORK_DIR / repo_name
    if not repo_path.exists():
        return {"status": "not_found", "repo": repo_name}

    cmd = ["grep", "-rn", "--include", file_pattern, query, str(repo_path)] if file_pattern else \
          ["grep", "-rn", query, str(repo_path)]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

    matches = []
    for line in lines[:50]:
        parts = line.split(":", 2)
        if len(parts) >= 3:
            fpath = parts[0].replace(str(repo_path) + "/", "")
            matches.append({"file": fpath, "line": parts[1], "text": parts[2].strip()})

    return {"matches": matches, "count": len(matches), "truncated": len(lines) > 50}


def get_repo_structure(repo_name: str) -> dict:
    """Get a high-level overview of the repo structure — directories, key files, languages.

    Args:
        repo_name: Name of the cloned repo.
    """
    repo_path = WORK_DIR / repo_name
    if not repo_path.exists():
        return {"status": "not_found", "repo": repo_name}

    # top-level entries
    top_level = []
    for entry in sorted(repo_path.iterdir()):
        if entry.name.startswith("."):
            continue
        top_level.append({
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
        })

    # detect key files
    key_files = []
    for name in ["README.md", "README.rst", "CLAUDE.md", "SKILL.md",
                  "setup.py", "pyproject.toml", "package.json", "go.mod",
                  "pom.xml", "build.gradle", "Makefile", "Dockerfile",
                  "docker-compose.yaml", "docker-compose.yml",
                  ".env.example", "requirements.txt"]:
        if (repo_path / name).exists():
            key_files.append(name)

    # count by extension
    ext_counts: dict[str, int] = {}
    for f in repo_path.rglob("*"):
        if f.is_file() and not any(p.startswith(".") for p in f.parts):
            ext = f.suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    top_exts = sorted(ext_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "repo": repo_name,
        "top_level": top_level,
        "key_files": key_files,
        "languages": [{"ext": e, "count": c} for e, c in top_exts],
    }


def propose_knowledge(
    name: str,
    domain: str,
    content: str,
    source_repo: str,
    source_files: str,
    description: str,
    tags: str = "",
) -> dict:
    """Propose a knowledge doc discovered from code analysis.

    Saves as a draft and submits for review through the standard pipeline.

    Args:
        name: Kebab-case name for the knowledge doc.
        domain: Domain category (e.g. "api-contracts", "architecture").
        content: The knowledge doc markdown content.
        source_repo: Which repo this was discovered from.
        source_files: Comma-separated list of key files that informed this.
        description: What this knowledge doc captures and why it matters.
        tags: Comma-separated tags.
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from db.repository import ContributionRepository

    repo = ContributionRepository()

    try:
        import hashlib
        sha = hashlib.sha256(content.encode()).hexdigest()
        frontmatter = {
            "title": description,
            "domain": domain,
            "source_repo": source_repo,
            "source_files": source_files,
            "discovered_by": "code-analyst",
        }

        existing = repo.get_by_name("knowledge", name)
        if existing:
            c = repo.update_content(
                existing.id,
                content=content,
                updated_by="code-analyst",
                frontmatter=frontmatter,
                change_summary=f"Updated from {source_repo} analysis",
            )
            return {"status": "updated", "id": c.id, "name": name, "version": c.current_version}

        c = repo.create(
            type="knowledge",
            name=name,
            content=content,
            created_by="code-analyst",
            domain=domain,
            frontmatter=frontmatter,
            tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else [],
        )
        repo.submit_for_review(c.id)
        return {"status": "created_and_submitted", "id": c.id, "name": name}

    except Exception as e:
        return {"error": str(e)}


def propose_skill_update(
    skill_name: str,
    description: str,
    source_repo: str,
    suggested_changes: str,
) -> dict:
    """Propose an update to an existing skill based on code analysis findings.

    Does NOT directly modify the skill — creates a documented suggestion
    for a human reviewer.

    Args:
        skill_name: Name of the skill to update.
        description: What should change and why.
        source_repo: Which repo analysis prompted this.
        suggested_changes: The specific changes proposed (markdown).
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from db.repository import ContributionRepository

    repo = ContributionRepository()

    try:
        content = f"""# Skill Update Proposal: {skill_name}

**Source:** code analysis of `{source_repo}`
**Proposed by:** code-analyst agent

## What should change

{description}

## Suggested changes

{suggested_changes}
"""
        c = repo.create(
            type="knowledge",
            name=f"skill-update-proposal-{skill_name}",
            content=content,
            created_by="code-analyst",
            domain="skill-proposals",
            frontmatter={"proposal_for_skill": skill_name, "source_repo": source_repo},
            tags=["skill-proposal", "auto-discovered"],
        )
        repo.submit_for_review(c.id)
        return {"status": "proposal_submitted", "id": c.id, "for_skill": skill_name}

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# CODE ANALYST AGENT
# =============================================================================

code_analyst_agent = Agent(
    model="gemini-2.5-flash",
    name="code_analyst",
    description=(
        "Analyzes git repositories to discover knowledge and skill improvements. "
        "Use when asked to analyze a codebase, discover API patterns, extract "
        "architecture knowledge, or find gaps in existing skills and knowledge."
    ),
    instruction="""\
You are a code analyst agent. You clone and analyze git repositories to discover
knowledge that should be captured for the platform agent to use.

## Your workflow

1. **Clone** the repo with clone_repo.
2. **Understand the structure** — use get_repo_structure to get an overview,
   then read key files (README, config files, entry points).
3. **Discover knowledge** systematically:

   **API contracts:**
   - Find API route definitions, endpoint handlers, request/response schemas
   - Look for OpenAPI specs, Swagger files, or inline route definitions
   - Document: endpoint paths, methods, auth requirements, key parameters

   **Architecture patterns:**
   - Entry points, service boundaries, data flow
   - How authentication/authorization works
   - Error handling patterns, retry policies

   **Business rules:**
   - Validation logic, constraints, invariants
   - Domain-specific rules embedded in code comments or variable names
   - Hard-coded constants that represent policy (limits, thresholds)

   **Operational knowledge:**
   - How to build, test, deploy
   - Environment variables and their purposes
   - Dependencies and their roles

4. **Cross-reference with existing knowledge** — before proposing, check if the
   knowledge already exists (search by topic). Only propose what's genuinely new
   or corrects something outdated.

5. **Propose** using propose_knowledge (for new facts) or propose_skill_update
   (for skill improvements). Every proposal goes through human review.

## Rules

- **Read code, don't run it.** You analyze; you don't execute application code.
- **One topic per knowledge doc.** Prefer many small, focused docs.
- **Write for the agent.** The consumer of your knowledge docs is an AI agent,
  not a human developer. State facts and actionable rules, not background.
- **Cite your sources.** Always include which files informed each finding.
- **Don't duplicate.** Check existing knowledge before proposing.
- **Propose, don't deploy.** Every finding goes through review — propose_knowledge
  and propose_skill_update both submit for approval.
""",
    tools=[
        clone_repo,
        list_repo_files,
        read_repo_file,
        search_repo,
        get_repo_structure,
        propose_knowledge,
        propose_skill_update,
    ],
)
