# Submitting a skill PR via git CLI

After the skill folder is drafted and validation passes, open a PR using git
and the GitHub CLI (`gh`). Adapt the `gh` commands for GitLab (`glab`) or
Bitbucket as needed.

## Prerequisites

- The skills repo is cloned locally and you are inside it.
- `git` and `gh` (GitHub CLI) are available.
- Authenticated (`gh auth status` succeeds).

## Steps

### 1. Create a branch

Use a predictable naming convention so reviewers can tell at a glance what a
branch carries.

```bash
SKILL_NAME="<kebab-case skill name>"
BRANCH="skill/${SKILL_NAME}"
git checkout -b "$BRANCH" main
```

### 2. Stage only the skill folder

Never stage files outside the skill folder. This is a guardrail — the
service-account identity should also have path-scoped write access, but
belt-and-suspenders.

```bash
git add "skills/${SKILL_NAME}/"
```

Verify nothing unexpected is staged:

```bash
git diff --cached --name-only
# every line should start with skills/<skill-name>/
```

### 3. Commit

```bash
git commit -m "skill(${SKILL_NAME}): add new skill

Drafted via skill-creator by <ops user name/team>.
AI-assisted — review the SKILL.md and eval cases."
```

### 4. Push and open the PR

```bash
git push -u origin "$BRANCH"

gh pr create \
  --title "skill(${SKILL_NAME}): new skill contribution" \
  --body "$(cat <<'EOF'
## Summary
- **Skill:** <skill name>
- **Requested by:** <ops user name/team>
- **AI-drafted:** yes (via skill-creator)

## What it does
<one-line from the skill description>

## Eval coverage
- N functional cases
- N edge cases
- N safety/refusal cases

## Checklist
- [ ] Reviewer: skill guidelines are accurate
- [ ] Reviewer: eval cases cover the critical paths
- [ ] Reviewer: no executable code in the folder
- [ ] CI: all eval suites pass
EOF
)"
```

### 5. Report back

Tell the user: the PR URL, that it's now awaiting review, and that CI will
run the eval suites automatically. They don't need to do anything else.

## GitLab variant

Replace step 4 with:

```bash
git push -u origin "$BRANCH"
glab mr create \
  --title "skill(${SKILL_NAME}): new skill contribution" \
  --description "..."
```

## Guardrails (enforced outside this skill)

These are platform-level controls, not things the skill-creator checks:

- **Branch protection:** main/master requires CI pass + 1 human approval.
- **Service account scope:** the identity used to push can only write to
  `skills/` — cannot push to `src/`, `tools/`, `.github/`, etc.
- **CI gate:** the PR triggers static checks + the 3 eval suites. The skill
  cannot self-merge.
