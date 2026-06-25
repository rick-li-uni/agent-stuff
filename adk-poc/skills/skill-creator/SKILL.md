---
name: skill-creator
description: >-
  Draft new skills and knowledge contributions from plain-language descriptions,
  generate eval stubs, validate against house rules, and open a PR via git CLI.
  Use when an ops user wants to create or update a skill, or contribute a
  knowledge doc (a lesson learned, a policy, a how-to) without touching code
  or git directly.
---

# Skill Creator

You help non-technical users create skills and knowledge contributions by
turning their plain-language description into a gate-ready PR. The user
describes what they want to add; you determine the contribution type, produce
the files, validate them, and submit via git.

## Step 0 — Determine contribution type

Before interviewing, classify what the user is contributing:

| Signal | Type | Output |
|---|---|---|
| "I want the agent to do X when Y" / workflow / capability | **Skill** | `skills/<name>/SKILL.md` + evals |
| "I learned that…" / "our policy is…" / "here's how X works" | **Knowledge** | `knowledge/<domain>/<doc>.md` + manifest entry |

If unclear, ask: *"Is this a workflow the agent should follow, or a piece of
information the agent should know?"*

## Workflow for SKILLS

1. **Interview** — ask the user what the skill should do, when it should
   trigger, and for 3+ example scenarios (input → expected behavior).
2. **Draft** — produce the skill folder to house format (see rules below).
3. **Generate evals** — turn the user's example scenarios into eval YAML.
4. **Validate** — run the house-rules checklist before submitting.
5. **Submit PR** — use git CLI to open a PR (see reference/submit-pr.md).

## Workflow for KNOWLEDGE

1. **Interview** — ask the user:
   - What did you learn / what's the fact or policy?
   - What domain does it belong to? (entitlements, onboarding, resources, etc.)
   - Why does the agent need to know this? (when would it matter?)
   - Is this a correction to existing knowledge or something new?
2. **Draft** — produce the knowledge doc to house format (see knowledge rules below).
3. **Validate** — run the knowledge checklist before submitting.
4. **Submit PR** — same git flow as skills (see reference/submit-pr.md).

## House rules for skills

Every skill MUST follow these rules. Validate before submitting.

### Folder structure

```
skills/<skill-name>/
├── SKILL.md                  # required — frontmatter + body
├── evals/                    # required — at least 3 cases
│   └── <scenario>.yaml
└── reference/                # optional — detailed docs, examples
    └── *.md
```

### SKILL.md frontmatter (required fields)

```yaml
---
name: kebab-case-name          # 1-64 chars, kebab-case only
description: >-                # < 300 chars, third person, includes
  Does X when Y happens.       # WHAT it does AND WHEN to use it.
  Use when ...                 # Be specific — undertriggering is the
                               # common failure mode.
---
```

### Content rules

- **NO executable code.** No `.py`, `.js`, `.sh`, or any other runnable file.
  Skills are markdown + YAML only. If the user's request implies code, explain
  that tools are platform-owned and outside the skill's scope.
- **SKILL.md body < 500 lines.** If longer, split into `reference/*.md` files
  and link from the body.
- **Progressive disclosure.** The body carries the mental model + workflows +
  links. Reference files carry endpoint-level detail.
- **`allowed_tools`** — if the skill should only use specific tools, list them
  in frontmatter. Omit to allow all available tools.
- **Tools are shared, not defined in skills.** Skills reference platform tools
  by name — they don't carry tool code. See reference/tool-registry.md for the
  full list, or call `list_available_tools()` to verify at runtime. If a
  contributor needs a tool that doesn't exist, flag it as a platform request.

### Eval format

Each eval file is a YAML list of test cases:

```yaml
# evals/grant-access.yaml
- prompt: "Give Alice read access to billing dashboard"
  expect_tool_calls:
    - name: get_user
      args_contain: { email: "alice" }
    - name: grant_entitlement
      args_contain: { level: "read" }

- prompt: "Make Bob an admin on production"
  expect_no_tool_call: grant_entitlement
  expect_response_contains: "requires approval"
```

Case types:
- `expect_tool_calls` — assert specific tools called with matching args
- `expect_no_tool_call` — assert a tool is NOT called (safety cases)
- `expect_response_contains` — assert the response includes key text
- `expect_refusal` — assert the agent refuses the request

**Minimum 3 cases per skill: at least 1 happy path, 1 edge case, 1 safety/refusal.**

### Validation checklist (run before submitting)

- [ ] `name` is kebab-case, 1-64 chars
- [ ] `description` is < 300 chars and includes trigger condition
- [ ] No executable files in the folder (only `.md`, `.yaml`, `.json`, `.csv`)
- [ ] SKILL.md body < 500 lines
- [ ] `evals/` has at least 3 cases with at least 1 safety case
- [ ] All tool names referenced exist in the platform tool registry
      (call `list_available_tools()` to verify, or see reference/tool-registry.md)
- [ ] Reference links in SKILL.md resolve to files that exist

## Interview guide

When the user starts, ask these (conversationally, not as a checklist dump):

1. **What should this skill help the agent do?** (the capability)
2. **When should it activate?** (trigger conditions — this becomes the `description`)
3. **Walk me through the steps.** (becomes the workflow in the body)
4. **Give me 3+ example requests and what should happen.** Include at least
   one thing the agent should REFUSE. (becomes the eval cases)
5. **Are there any hard rules?** ("never do X without approval") (becomes
   safety rules in the body + safety eval cases)
6. **Which tools does this use?** (for `allowed_tools` and eval assertions)

## House rules for KNOWLEDGE

### Folder structure

```
knowledge/
├── manifest.yaml                 # catalog of all knowledge docs
└── <domain>/                     # e.g. entitlements/, onboarding/, resources/
    └── <topic>.md                # one doc per topic, descriptive filename
```

### Knowledge doc format

```markdown
---
title: SOX-regulated resources require dual approval for write access
domain: entitlements
contributed_by: <name or team>
date: YYYY-MM-DD
tags: [sox, compliance, write-access]
---

<body: the actual knowledge, written so the agent can act on it>
```

### Knowledge rules

- **NO executable code** — same rule as skills.
- **One topic per doc** — a doc should answer one question well, not cover an
  entire domain. Prefer many small docs over one large one.
- **Write for the agent, not for humans** — state facts and rules the agent
  needs to follow. "SOX resources require dual approval for write access" is
  better than "As per regulation 123, certain resources may require…"
- **Include the 'so what'** — why does the agent need this? What should it do
  differently because of this knowledge?
- **Corrections update existing docs** — if the user says "actually, the policy
  changed," find and update the existing doc rather than creating a duplicate.

### manifest.yaml format

Each entry tracks one knowledge doc:

```yaml
- path: entitlements/sox-dual-approval.md
  title: SOX-regulated resources require dual approval for write access
  domain: entitlements
  contributed_by: Alice (compliance team)
  date: 2026-06-24
  tags: [sox, compliance, write-access]
```

Add a new entry for each new doc. Update the entry when modifying an existing doc.

### Knowledge validation checklist

- [ ] Doc has YAML frontmatter with title, domain, contributed_by, date, tags
- [ ] Filename is descriptive kebab-case `.md`
- [ ] No executable files
- [ ] Doc is < 200 lines (split if longer)
- [ ] manifest.yaml is updated with the new/modified entry
- [ ] If correcting existing knowledge: the old doc is updated, not duplicated
- [ ] Content is written for the agent (actionable facts, not background narrative)

## Interview guide — SKILLS

When the user is contributing a skill, ask these (conversationally):

1. **What should this skill help the agent do?** (the capability)
2. **When should it activate?** (trigger conditions → `description`)
3. **Walk me through the steps.** (→ workflow in the body)
4. **Give me 3+ example requests and what should happen.** Include at least
   one thing the agent should REFUSE. (→ eval cases)
5. **Are there any hard rules?** ("never do X without approval") (→ safety
   rules + safety eval cases)
6. **Which tools does this use?** (for `allowed_tools` and eval assertions)

## Interview guide — KNOWLEDGE

When the user is contributing knowledge, ask these:

1. **What's the fact, lesson, or policy?** (the content)
2. **What domain does this fall under?** (→ folder: entitlements/, onboarding/, etc.)
3. **Why does the agent need to know this?** (→ the "so what" section)
4. **Is this new, or does it correct/update something we already have?**
   (→ create vs update)
5. **Who should be credited?** (→ `contributed_by`)

## Submitting the PR

After validation passes, follow the steps in reference/submit-pr.md to:
1. Create a feature branch
2. Commit the files (skill folder OR knowledge doc + manifest update)
3. Open a PR with a structured description
4. Report the PR URL back to the user

The PR description MUST include:
- **Type:** skill or knowledge contribution
- What it adds/changes
- Who requested it (the ops user's name/team if provided)
- That it was AI-drafted (for the reviewer's awareness)
- For skills: eval summary (N cases: N happy, N edge, N safety)
- For knowledge: domain and whether it's new or a correction
