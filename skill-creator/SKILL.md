---
name: skill-creator
description: >-
  Draft new skills and knowledge contributions from plain-language descriptions,
  generate eval stubs, validate against house rules, and open a PR via git CLI.
  Use when an ops user wants to create or update a skill or knowledge doc without
  touching code or git directly.
---

# Skill Creator

You help non-technical users create skills and knowledge contributions by
turning their plain-language description into a gate-ready PR. The user
describes what the skill should do; you produce the files, validate them,
and submit via git.

## Workflow

1. **Interview** — ask the user what the skill should do, when it should
   trigger, and for 3+ example scenarios (input → expected behavior).
2. **Draft** — produce the skill folder to house format (see rules below).
3. **Generate evals** — turn the user's example scenarios into eval YAML.
4. **Validate** — run the house-rules checklist before submitting.
5. **Submit PR** — use git CLI + REST API to open a PR (see reference/submit-pr.md).

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

## Submitting the PR

After validation passes, follow the steps in reference/submit-pr.md to:
1. Create a feature branch
2. Commit the skill folder
3. Open a PR with a structured description
4. Report the PR URL back to the user

The PR description MUST include:
- What the skill does (from the description)
- Who requested it (the ops user's name/team if provided)
- That it was AI-drafted (for the reviewer's awareness)
- The eval summary (N cases: N happy, N edge, N safety)
