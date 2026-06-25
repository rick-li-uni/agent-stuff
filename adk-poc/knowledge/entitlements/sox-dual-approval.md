---
title: SOX-regulated resources require dual approval for write access
domain: entitlements
contributed_by: Alice (compliance team)
date: 2026-06-24
tags: [sox, compliance, write-access]
---

Any resource tagged as SOX-regulated requires **two independent approvers** for
write-level access grants. Read access follows the standard single-approval flow.

When a user requests write access to a SOX resource:
1. Do NOT call grant_entitlement directly.
2. Inform the user that SOX resources require dual approval.
3. Direct them to submit a request through the governance portal.

This applies regardless of the requester's seniority or role.
