# Resources API

## list_resources

List available resources, optionally filtered by type.

**Parameters:**
- `resource_type` (string, optional) — filter by type: "dashboard", "database", etc.

**Returns:**
- `resources: [{id, name, type}, ...]`
- `count: N`

**Example:**
```
list_resources(resource_type="dashboard")
→ {resources: [{id: "r-001", name: "billing-dashboard", type: "dashboard"}], count: 1}
```
