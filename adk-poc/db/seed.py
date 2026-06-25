"""
Seed the database with the existing filesystem-based skills and knowledge.

Run after schema.sql:
    python -m db.seed
"""

from __future__ import annotations

import pathlib
import sys

from db.repository import ContributionRepository, get_conn


SKILLS_DIR = pathlib.Path(__file__).parent.parent / "skills"
KNOWLEDGE_DIR = pathlib.Path(__file__).parent.parent / "knowledge"


def seed_skill(repo: ContributionRepository, skill_dir: pathlib.Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return

    content = skill_md.read_text(encoding="utf-8")
    name = skill_dir.name

    # parse frontmatter
    frontmatter = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import yaml
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            body = content
    else:
        body = content

    # collect additional files
    files = {}
    for f in skill_dir.rglob("*"):
        if f.is_file() and f != skill_md:
            rel = str(f.relative_to(skill_dir))
            files[rel] = f.read_text(encoding="utf-8")

    existing = repo.get_by_name("skill", name)
    if existing:
        print(f"  Skill '{name}' already exists (id={existing.id}), skipping")
        return

    c = repo.create(
        type="skill",
        name=name,
        content=body,
        created_by="seed",
        frontmatter=frontmatter,
        files=files,
        tags=frontmatter.get("tags", []),
    )
    # auto-approve seed data
    repo.submit_for_review(c.id)
    repo.approve(c.id, 1, "seed", "Initial seed from filesystem")
    print(f"  Seeded skill: {name} (id={c.id})")


def seed_knowledge(repo: ContributionRepository, knowledge_dir: pathlib.Path) -> None:
    for md_file in knowledge_dir.rglob("*.md"):
        if md_file.name == "manifest.yaml":
            continue

        content = md_file.read_text(encoding="utf-8")
        rel_path = md_file.relative_to(knowledge_dir)
        domain = rel_path.parts[0] if len(rel_path.parts) > 1 else "general"
        name = md_file.stem

        # parse frontmatter
        frontmatter = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
            else:
                body = content
        else:
            body = content

        existing = repo.get_by_name("knowledge", name)
        if existing:
            print(f"  Knowledge '{name}' already exists (id={existing.id}), skipping")
            continue

        c = repo.create(
            type="knowledge",
            name=name,
            content=body,
            created_by=frontmatter.get("contributed_by", "seed"),
            domain=domain,
            frontmatter=frontmatter,
            tags=frontmatter.get("tags", []),
        )
        repo.submit_for_review(c.id)
        repo.approve(c.id, 1, "seed", "Initial seed from filesystem")
        print(f"  Seeded knowledge: {name} (id={c.id}, domain={domain})")


def main():
    conn = get_conn()
    repo = ContributionRepository(conn)

    print("Seeding skills...")
    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if skill_dir.is_dir():
                seed_skill(repo, skill_dir)

    print("\nSeeding knowledge...")
    if KNOWLEDGE_DIR.exists():
        seed_knowledge(repo, KNOWLEDGE_DIR)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
