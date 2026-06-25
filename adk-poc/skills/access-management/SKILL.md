---
name: access-management
description: >-
  Manage users, resources, and entitlements via the platform API. Use when
  granting or revoking a user's access to a resource, checking what a user
  is entitled to, or creating/looking up users and resources.
---

# Access Management

A **user** is granted access to a **resource** through an **entitlement**.

## Hard rules

- **NEVER grant `admin` level access automatically.** If the user requests
  admin access, refuse the tool call and direct them to the governance portal.
- Always confirm revocations before executing.
- Look up both the user AND the resource before creating an entitlement.

## Common workflows

### Grant a user access

1. Resolve the user → `get_user(email=...)`
2. Resolve the resource → `list_resources(resource_type=...)` or by name
3. Create the entitlement → `grant_entitlement(user_id=..., resource_id=..., level=...)`

### Check existing access

1. Resolve the user → `get_user(email=...)`
2. Check → `check_entitlement(user_id=..., resource_id=...)`

### Revoke access

1. Confirm with the user: "Are you sure you want to revoke X's access to Y?"
2. Only after confirmation → `revoke_entitlement(user_id=..., resource_id=...)`

## Detailed API reference

See reference/users.md, reference/resources.md, reference/entitlements.md.
