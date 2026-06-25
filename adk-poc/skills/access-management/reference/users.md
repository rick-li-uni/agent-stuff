# Users API

## get_user

Look up a user by email.

**Parameters:**
- `email` (string, required) — the user's corporate email

**Returns:**
- `status: "found"` + `user: {id, email, name}`
- `status: "not_found"` + `email`

**Example:**
```
get_user(email="alice@corp.com")
→ {status: "found", user: {id: "u-001", email: "alice@corp.com", name: "Alice"}}
```
