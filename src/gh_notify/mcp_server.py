"""FastMCP server for GitHub notification triage and work item tracking."""

from __future__ import annotations

import sqlite3

from mcp.server.fastmcp import FastMCP

from gh_notify import db, github, work_items_db
from gh_notify.models import Status, WorkItem, WorkItemStatus
from gh_notify.urls import parse_github_url, parse_short_ref

mcp = FastMCP(
    "gh-notify",
    instructions=(
        "GitHub notification triage — sync, filter, and manage notification state. "
        "Use sync_notifications first, then list_actionable to see what needs attention. "
        "Work items track multi-session work streams with linked GitHub entities. "
        "Use resolve_context to get full context for a work item, URL, or short ref."
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


# --- Work Items ---


@mcp.tool()
async def create_work_item(id: str, title: str, description: str = "") -> str:
    """Create a named work item to track a multi-session work stream.

    Args:
        id: Slug identifier (e.g. "serena-global-memories").
        title: Human-readable title.
        description: Optional longer description.
    """
    conn = db.connect()
    try:
        item = work_items_db.create_work_item(conn, id, title, description)
    except sqlite3.IntegrityError:
        return f"Work item '{id}' already exists."
    finally:
        conn.close()
    return f"Created work item '{item.id}': {item.title}"


@mcp.tool()
async def update_work_item(
    id: str,
    title: str | None = None,
    status: str | None = None,
    description: str | None = None,
    append_description: str | None = None,
) -> str:
    """Update a work item's fields.

    Args:
        id: Work item slug.
        title: New title (optional).
        status: New status: "active", "paused", or "completed" (optional).
        description: Replace description entirely (optional).
        append_description: Append to existing description (optional, takes precedence over description).
    """
    ws = None
    if status is not None:
        try:
            ws = WorkItemStatus(status)
        except ValueError:
            return f"Invalid status '{status}'. Must be: active, paused, completed."

    conn = db.connect()
    try:
        item = work_items_db.update_work_item(
            conn, id,
            title=title,
            status=ws,
            description=description,
            append_description=append_description,
        )
    finally:
        conn.close()

    if item is None:
        return f"Work item '{id}' not found."
    return f"Updated '{item.id}': {item.title} [{item.status.value}]"


@mcp.tool()
async def list_work_items(status: str | None = None) -> str:
    """List work items with link counts.

    Args:
        status: Filter by status: "active", "paused", or "completed" (optional).
    """
    ws = None
    if status is not None:
        try:
            ws = WorkItemStatus(status)
        except ValueError:
            return f"Invalid status '{status}'. Must be: active, paused, completed."

    conn = db.connect()
    try:
        items = work_items_db.list_work_items(conn, status=ws)
    finally:
        conn.close()

    if not items:
        return "No work items found."

    lines = []
    for item in items:
        lines.append(
            f"[{item.status.value.upper()}] {item.id} — {item.title} ({item.link_count} links)"
        )
        if item.description:
            # Show first line of description
            first_line = item.description.split("\n")[0][:100]
            lines.append(f"  {first_line}")
    return "\n".join(lines)


@mcp.tool()
async def link_entity(
    work_item_id: str,
    url: str,
    relationship: str = "related",
    notes: str = "",
) -> str:
    """Link a GitHub URL, short ref, or work item slug to a work item.

    Auto-detects entity type and normalizes URLs. Idempotent — re-linking
    the same URL updates the relationship and notes.

    Args:
        work_item_id: Work item slug.
        url: GitHub URL, short ref (owner/repo#N), or work_item://slug.
        relationship: How the entity relates: tracks, blocked_by, implements, related.
        notes: Optional notes about the link.
    """
    conn = db.connect()
    try:
        link = work_items_db.upsert_link(conn, work_item_id, url, relationship, notes)
    except sqlite3.IntegrityError:
        return f"Work item '{work_item_id}' not found."
    finally:
        conn.close()

    return f"Linked {link.entity_ref or link.entity_url} → {work_item_id} [{link.relationship}]"


@mcp.tool()
async def unlink_entity(work_item_id: str, url: str) -> str:
    """Remove a link between an entity and a work item.

    Args:
        work_item_id: Work item slug.
        url: The URL or short ref that was linked.
    """
    conn = db.connect()
    try:
        ok = work_items_db.delete_link(conn, work_item_id, url)
    finally:
        conn.close()

    if not ok:
        return f"No link found for '{url}' on work item '{work_item_id}'."
    return f"Unlinked '{url}' from '{work_item_id}'."


@mcp.tool()
async def resolve_context(identifier: str) -> str:
    """Resolve full context for a work item, GitHub URL, or short ref.

    Resolution cascade:
    1. Direct work_items.id lookup — shows item + all links + notification cross-refs
    2. Parse as GitHub URL — finds work items linked to that URL + notification status
    3. Parse as full short ref (owner/repo#N) — expands to URL, same as #2
    4. Partial ref search — LIKE match on links.entity_ref

    Args:
        identifier: Work item slug, GitHub URL, or short ref.
    """
    conn = db.connect()
    try:
        return _resolve(conn, identifier)
    finally:
        conn.close()


def _resolve(conn: sqlite3.Connection, identifier: str) -> str:
    """Resolution cascade implementation."""
    # [1] Direct work item lookup
    item = work_items_db.get_work_item(conn, identifier)
    if item is not None:
        return _format_work_item_context(conn, item)

    # [2] Parse as GitHub URL
    parsed = parse_github_url(identifier)
    if parsed:
        return _resolve_from_parsed(conn, parsed.canonical_url, parsed.full_repo, parsed.number, parsed.short_ref)

    # [3] Parse as short ref
    parsed = parse_short_ref(identifier)
    if parsed:
        return _resolve_from_parsed(conn, parsed.canonical_url, parsed.full_repo, parsed.number, parsed.short_ref)

    # [4] Partial ref search
    results = work_items_db.find_work_items_by_ref(conn, identifier)
    if results:
        lines = [f"Partial ref match for '{identifier}':", ""]
        seen_items: set[str] = set()
        for wi, link in results:
            if wi.id not in seen_items:
                lines.append(f"  [{wi.status.value.upper()}] {wi.id} — {wi.title}")
                seen_items.add(wi.id)
            lines.append(f"    {link.relationship}: {link.entity_ref or link.entity_url}")
        return "\n".join(lines)

    return f"No context found for '{identifier}'."


def _resolve_from_parsed(
    conn: sqlite3.Connection,
    canonical_url: str,
    full_repo: str,
    number: int | None,
    short_ref: str,
) -> str:
    """Resolve context from a parsed URL: find linked work items + notification status."""
    lines = [f"Context for {short_ref}:", ""]

    # Find work items linked to this URL
    results = work_items_db.find_work_items_by_url(conn, canonical_url)
    if not results and number is not None:
        # For numbered entities (PRs/issues), try exact ref match since short ref
        # normalizes to /issues/ but link may be stored as /pull/. Only safe when
        # we have a number — non-numbered URLs (commits, repos) produce ambiguous
        # short_refs like "owner/repo" that would false-match unrelated links.
        results = work_items_db.find_work_items_by_ref_exact(conn, short_ref)

    if results:
        lines.append("Work items:")
        seen_items: set[str] = set()
        for wi, link in results:
            if wi.id not in seen_items:
                lines.append(f"  [{wi.status.value.upper()}] {wi.id} — {wi.title}")
                seen_items.add(wi.id)
            lines.append(f"    {link.relationship}: {link.entity_ref or link.entity_url}")
        lines.append("")

    # Cross-reference notifications
    if full_repo:
        notifications = db.find_notifications_by_repo(conn, full_repo, number)
        if notifications:
            lines.append("Notifications:")
            for n in notifications[:5]:  # Cap at 5
                status_tag = n.status.value.upper()
                lines.append(f"  [{status_tag}] {n.thread_id} | {n.reason} | {n.subject_title}")
                if n.notes:
                    lines.append(f"    Notes: {n.notes}")
            lines.append("")

    if len(lines) <= 2:  # Only header + blank line
        return f"No context found for '{short_ref}'."

    return "\n".join(lines)


def _format_work_item_context(conn: sqlite3.Connection, item: WorkItem) -> str:
    """Format full context for a work item."""
    lines = [
        f"Work Item: {item.id}",
        f"Title: {item.title}",
        f"Status: {item.status.value}",
    ]

    if item.description:
        lines.append(f"Description: {item.description}")
    lines.append("")

    # Links
    links = work_items_db.get_links_for_work_item(conn, item.id)
    if links:
        lines.append("Links:")
        for link in links:
            ref = link.entity_ref or link.entity_url
            line = f"  {link.relationship}: {ref} [{link.entity_type}]"
            if link.notes:
                line += f" — {link.notes}"
            lines.append(line)
        lines.append("")

    # Reverse links (other work items pointing at this one)
    reverse = work_items_db.find_reverse_links(conn, item.id)
    if reverse:
        lines.append("Referenced by:")
        for wi, link in reverse:
            lines.append(f"  {wi.id} ({link.relationship})")
        lines.append("")

    # Cross-reference notifications for each linked entity
    seen_threads: set[str] = set()
    notification_lines: list[str] = []
    for link in links:
        if link.entity_repo:
            parsed = parse_github_url(link.entity_url)
            number = parsed.number if parsed else None
            notifications = db.find_notifications_by_repo(conn, link.entity_repo, number)
            for n in notifications[:3]:
                if n.thread_id not in seen_threads:
                    seen_threads.add(n.thread_id)
                    status_tag = n.status.value.upper()
                    notification_lines.append(
                        f"  [{status_tag}] {n.thread_id} | {n.repo} | {n.reason} | {n.subject_title}"
                    )

    if notification_lines:
        lines.append("Related notifications:")
        lines.extend(notification_lines)
        lines.append("")

    return "\n".join(lines)


def main():
    """Entry point for the MCP server."""
    mcp.run()
