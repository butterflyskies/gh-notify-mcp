"""FastMCP server for GitHub notification triage."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from gh_notify import db, github
from gh_notify.models import Status

mcp = FastMCP(
    "gh-notify",
    instructions=(
        "GitHub notification triage — sync, filter, and manage notification state. "
        "Use sync_notifications first, then list_actionable to see what needs attention."
    ),
)


@mcp.tool()
async def sync_notifications() -> str:
    """Fetch GitHub notifications and upsert into local database.

    New threads get status 'new'. Existing threads keep their current status
    but get metadata (title, timestamps) updated.

    Returns summary of new and updated counts.
    """
    notifications = await github.fetch_notifications()
    conn = db.connect()
    try:
        result = db.upsert(conn, notifications)
    finally:
        conn.close()

    parts = []
    if result["new"]:
        parts.append(f"{result['new']} new")
    if result["updated"]:
        parts.append(f"{result['updated']} updated")
    if not parts:
        return "No notifications found."
    return f"Synced: {', '.join(parts)}. Total fetched: {len(notifications)}."


@mcp.tool()
async def list_actionable(
    repo: str | None = None,
    reason: str | None = None,
    subject_type: str | None = None,
) -> str:
    """List notifications that need attention (status: new or triaged).

    Args:
        repo: Filter by repository (e.g. "butterflyskies/serena").
        reason: Filter by notification reason (mention, author, comment, ci_activity, assign).
        subject_type: Filter by subject type (Issue, PullRequest, CheckSuite).
    """
    conn = db.connect()
    try:
        items = db.list_actionable(conn, repo=repo, reason=reason, subject_type=subject_type)
    finally:
        conn.close()

    if not items:
        return "No actionable notifications."

    lines = []
    for n in items:
        status_tag = n.status.value.upper()
        lines.append(f"[{status_tag}] {n.thread_id} | {n.repo} | {n.subject_type} | {n.reason} | {n.subject_title}")
        if n.notes:
            lines.append(f"  Notes: {n.notes}")
    return "\n".join(lines)


@mcp.tool()
async def mark_triaged(thread_id: str, notes: str | None = None) -> str:
    """Mark a notification as triaged (acknowledged, will act on later).

    Args:
        thread_id: The notification thread ID.
        notes: Optional notes about the notification.
    """
    conn = db.connect()
    try:
        ok = db.set_status(conn, thread_id, Status.TRIAGED, notes=notes)
    finally:
        conn.close()

    if not ok:
        return f"Thread {thread_id} not found."
    return f"Thread {thread_id} marked as triaged."


@mcp.tool()
async def mark_acted(thread_id: str, skip_github: bool = False) -> str:
    """Mark a notification as acted upon. Marks read on GitHub by default.

    Args:
        thread_id: The notification thread ID.
        skip_github: If True, skip marking read on GitHub (for offline/testing).
    """
    conn = db.connect()
    try:
        ok = db.set_status(conn, thread_id, Status.ACTED)
    finally:
        conn.close()

    if not ok:
        return f"Thread {thread_id} not found."

    if not skip_github:
        try:
            await github.mark_thread_read(thread_id)
        except RuntimeError as e:
            return f"Thread {thread_id} marked as acted locally, but failed to mark read on GitHub: {e}"

    return f"Thread {thread_id} marked as acted."


@mcp.tool()
async def dismiss(thread_id: str, reason: str | None = None, skip_github: bool = False) -> str:
    """Dismiss a notification. Marks read on GitHub by default.

    Args:
        thread_id: The notification thread ID.
        reason: Optional reason for dismissing.
        skip_github: If True, skip marking read on GitHub (for offline/testing).
    """
    conn = db.connect()
    try:
        ok = db.set_status(conn, thread_id, Status.DISMISSED, notes=reason)
    finally:
        conn.close()

    if not ok:
        return f"Thread {thread_id} not found."

    if not skip_github:
        try:
            await github.mark_thread_read(thread_id)
        except RuntimeError as e:
            return f"Thread {thread_id} dismissed locally, but failed to mark read on GitHub: {e}"

    return f"Thread {thread_id} dismissed."


@mcp.tool()
async def get_stats() -> str:
    """Get summary counts of notifications by status, repository, and reason."""
    conn = db.connect()
    try:
        stats = db.get_stats(conn)
    finally:
        conn.close()

    if stats["total"] == 0:
        return "No notifications in database. Run sync_notifications first."

    lines = [f"Total: {stats['total']}", ""]

    lines.append("By status:")
    for status, count in sorted(stats["by_status"].items()):
        lines.append(f"  {status}: {count}")

    lines.append("")
    lines.append("By repo:")
    for repo, count in stats["by_repo"].items():
        lines.append(f"  {repo}: {count}")

    lines.append("")
    lines.append("By reason:")
    for reason, count in stats["by_reason"].items():
        lines.append(f"  {reason}: {count}")

    return "\n".join(lines)


def main():
    """Entry point for the MCP server."""
    mcp.run()
