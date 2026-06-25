# Entitlements API

## grant_entitlement

Grant a user access to a resource at a specific level.

**SAFETY:** `level="admin"` is NEVER auto-approved. The tool returns a rejection
and the agent must direct the user to the governance portal.

**Parameters:**
- `user_id` (string, required) — the user's ID from get_user
- `resource_id` (string, required) — the resource's ID from list_resources
- `level` (string, required) — "read", "write", or "admin"

**Returns:**
- `status: "granted"` + the entitlement object
- `status: "rejected"` + reason (for admin requests)

## check_entitlement

Check what access level a user has on a resource.

**Parameters:**
- `user_id` (string, required)
- `resource_id` (string, required)

**Returns:**
- `status: "found"` + entitlement
- `status: "none"`

## revoke_entitlement

Remove a user's access to a resource. **Always confirm with the user first.**

**Parameters:**
- `user_id` (string, required)
- `resource_id` (string, required)

**Returns:**
- `status: "revoked"` + count removed
- `status: "not_found"`
