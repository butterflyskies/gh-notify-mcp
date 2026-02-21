# gh-notify-mcp

GitHub notification triage MCP server with SQLite state tracking.

Syncs GitHub notifications via `gh` CLI and tracks triage state (new / triaged / acted / dismissed) locally in SQLite. Exposes 6 MCP tools so Claude Code can filter already-handled notifications instead of re-processing them every session.

## Tools

| Tool | Purpose |
|------|---------|
| `sync_notifications` | Fetch notifications from GitHub, upsert into SQLite |
| `list_actionable` | Return `new` + `triaged` items (with optional repo/reason/type filters) |
| `mark_triaged` | Mark a thread as triaged, with optional notes |
| `mark_acted` | Mark as acted; marks read on GitHub by default |
| `dismiss` | Dismiss a thread; marks read on GitHub by default |
| `get_stats` | Summary counts by status, repo, and reason |

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
