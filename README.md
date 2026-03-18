# gh-notify-mcp

GitHub notification triage MCP server with SQLite state tracking.

Syncs GitHub notifications via `gh` CLI and tracks triage state (new / triaged / acted / dismissed) locally in SQLite. Work items pre-cache cross-session context so `resolve_context("my-feature")` returns the full picture instantly. Exposes 12 MCP tools for notification triage and work item tracking.

## Tools

### Notification Triage

| Tool | Purpose |
|------|---------|
| `sync_notifications` | Fetch notifications from GitHub, upsert into SQLite |
| `list_actionable` | Return `new` + `triaged` items (with optional repo/reason/type filters) |
| `mark_triaged` | Mark a thread as triaged, with optional notes |
| `mark_acted` | Mark as acted; marks read on GitHub by default |
| `dismiss` | Dismiss a thread; marks read on GitHub by default |
| `get_stats` | Summary counts by status, repo, and reason |

### Work Items + Context Resolution

| Tool | Purpose |
|------|---------|
| `create_work_item` | Create a named work item (`id`, `title`, `description?`) |
| `update_work_item` | Update fields; `append_description` adds without replacing |
| `list_work_items` | List work items with link counts, optionally filtered by status |
| `link_entity` | Link a GitHub URL/short ref/work item slug. Auto-detects entity type. Idempotent. |
| `unlink_entity` | Remove a link between an entity and a work item |
| `resolve_context` | Full context bundle: work item slug, GitHub URL, or short ref. Cross-refs notifications. |

## Setup

Add to `~/.claude.json` under `mcpServers`:

```json
"gh-notify": {
  "type": "stdio",
  "command": "uv",
  "args": ["run", "--directory", "/path/to/gh-notify-mcp", "--extra", "mcp", "gh-notify-mcp"],
  "env": {
    "GH_CONFIG_DIR": "/path/to/gh-config"
  }
}
```

## Configuration

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `GH_CONFIG_DIR` | `~/.config/gh` | GitHub CLI identity |
| `GH_NOTIFY_GH_PATH` | `gh` | Path to gh binary |
| `GH_NOTIFY_DB_DIR` | `~/.local/share/gh-notify` | SQLite database directory |

## Development

```bash
uv run --extra dev pytest -v
```
