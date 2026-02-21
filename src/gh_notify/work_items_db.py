"""SQLite CRUD for work items and entity links."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from gh_notify.models import Link, WorkItem, WorkItemStatus
from gh_notify.urls import detect_entity_type, normalize_url, parse_github_url, parse_short_ref


def create_work_item(
    conn: sqlite3.Connection,
    id: str,
    title: str,
    description: str = "",
) -> WorkItem:
    """Create a new work item. Raises sqlite3.IntegrityError if id already exists."""
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO work_items (id, title, status, description, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (id, title, WorkItemStatus.ACTIVE.value, description, now, now),
    )
    conn.commit()
    return WorkItem(
        id=id,
        title=title,
        status=WorkItemStatus.ACTIVE,
        description=description,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


def get_work_item(conn: sqlite3.Connection, id: str) -> WorkItem | None:
    """Get a work item by id."""
    row = conn.execute("SELECT * FROM work_items WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    return _row_to_work_item(row)


def update_work_item(
    conn: sqlite3.Connection,
    id: str,
    *,
    title: str | None = None,
    status: WorkItemStatus | None = None,
    description: str | None = None,
    append_description: str | None = None,
) -> WorkItem | None:
    """Update a work item's fields. Returns None if not found."""
    existing = get_work_item(conn, id)
    if existing is None:
        return None

    new_title = title if title is not None else existing.title
    new_status = status if status is not None else existing.status
    if append_description is not None:
        sep = "\n\n" if existing.description else ""
        new_description = existing.description + sep + append_description
    elif description is not None:
        new_description = description
    else:
        new_description = existing.description

    now = datetime.now().isoformat()
    conn.execute(
        """UPDATE work_items SET title = ?, status = ?, description = ?, updated_at = ?
           WHERE id = ?""",
        (new_title, new_status.value, new_description, now, id),
    )
    conn.commit()
    return WorkItem(
        id=id,
        title=new_title,
        status=new_status,
        description=new_description,
        created_at=existing.created_at,
        updated_at=datetime.fromisoformat(now),
    )


def list_work_items(
    conn: sqlite3.Connection,
    status: WorkItemStatus | None = None,
) -> list[WorkItem]:
    """List work items, optionally filtered by status, with link counts."""
    query = """
        SELECT w.*, COUNT(l.id) as link_count
        FROM work_items w
        LEFT JOIN links l ON l.work_item_id = w.id
    """
    params: list[Any] = []
    if status is not None:
        query += " WHERE w.status = ?"
        params.append(status.value)
    query += " GROUP BY w.id ORDER BY w.updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    items = []
    for row in rows:
        item = _row_to_work_item(row)
        item.link_count = row["link_count"]
        items.append(item)
    return items


def _resolve_url_and_metadata(url_or_ref: str) -> tuple[str, str, str, str]:
    """Resolve a URL, short ref, or work_item:// slug into (canonical_url, entity_type, entity_repo, entity_ref)."""
    # Work item slug
    if url_or_ref.startswith("work_item://"):
        slug = url_or_ref[len("work_item://"):]
        return url_or_ref, "work_item", "", slug

    # Try as GitHub URL first
    parsed = parse_github_url(url_or_ref)
    if parsed:
        return parsed.canonical_url, parsed.entity_type, parsed.full_repo, parsed.short_ref

    # Try as short ref
    parsed = parse_short_ref(url_or_ref)
    if parsed:
        return parsed.canonical_url, parsed.entity_type, parsed.full_repo, parsed.short_ref

    # Fallback: use as-is
    entity_type = detect_entity_type(url_or_ref) or "unknown"
    return url_or_ref, entity_type, "", ""


def upsert_link(
    conn: sqlite3.Connection,
    work_item_id: str,
    url_or_ref: str,
    relationship: str = "related",
    notes: str = "",
) -> Link:
    """Link an entity to a work item. Idempotent: re-linking updates relationship/notes."""
    canonical_url, entity_type, entity_repo, entity_ref = _resolve_url_and_metadata(url_or_ref)

    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO links (work_item_id, entity_type, entity_url, entity_repo, entity_ref,
                              relationship, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(work_item_id, entity_url) DO UPDATE SET
               relationship = excluded.relationship,
               notes = excluded.notes""",
        (work_item_id, entity_type, canonical_url, entity_repo, entity_ref,
         relationship, notes, now),
    )
    # Touch work item updated_at
    conn.execute(
        "UPDATE work_items SET updated_at = ? WHERE id = ?",
        (now, work_item_id),
    )
    conn.commit()
    return Link(
        work_item_id=work_item_id,
        entity_type=entity_type,
        entity_url=canonical_url,
        entity_repo=entity_repo,
        entity_ref=entity_ref,
        relationship=relationship,
        notes=notes,
        created_at=datetime.fromisoformat(now),
    )


def delete_link(
    conn: sqlite3.Connection,
    work_item_id: str,
    url_or_ref: str,
) -> bool:
    """Remove a link. Returns False if not found.

    Tries canonical URL first, then falls back to exact entity_ref match
    to handle short refs that resolve to /issues/ but the link was stored
    as /pull/.
    """
    canonical_url, _, _, entity_ref = _resolve_url_and_metadata(url_or_ref)
    cursor = conn.execute(
        "DELETE FROM links WHERE work_item_id = ? AND entity_url = ?",
        (work_item_id, canonical_url),
    )
    if cursor.rowcount == 0 and entity_ref:
        cursor = conn.execute(
            "DELETE FROM links WHERE work_item_id = ? AND entity_ref = ?",
            (work_item_id, entity_ref),
        )
    conn.commit()
    return cursor.rowcount > 0


def get_links_for_work_item(conn: sqlite3.Connection, work_item_id: str) -> list[Link]:
    """Get all links for a work item."""
    rows = conn.execute(
        "SELECT * FROM links WHERE work_item_id = ? ORDER BY created_at",
        (work_item_id,),
    ).fetchall()
    return [_row_to_link(row) for row in rows]


def find_work_items_by_url(conn: sqlite3.Connection, url_or_ref: str) -> list[tuple[WorkItem, Link]]:
    """Find work items linked to a given URL or short ref."""
    canonical_url, _, _, _ = _resolve_url_and_metadata(url_or_ref)
    rows = conn.execute(
        """SELECT w.*, l.entity_type as l_entity_type, l.entity_url as l_entity_url,
                  l.entity_repo as l_entity_repo, l.entity_ref as l_entity_ref,
                  l.relationship as l_relationship, l.notes as l_notes,
                  l.created_at as l_created_at, l.work_item_id as l_work_item_id
           FROM work_items w
           JOIN links l ON l.work_item_id = w.id
           WHERE l.entity_url = ?""",
        (canonical_url,),
    ).fetchall()
    results = []
    for row in rows:
        item = _row_to_work_item(row)
        link = Link(
            work_item_id=row["l_work_item_id"],
            entity_type=row["l_entity_type"],
            entity_url=row["l_entity_url"],
            entity_repo=row["l_entity_repo"],
            entity_ref=row["l_entity_ref"],
            relationship=row["l_relationship"],
            notes=row["l_notes"],
            created_at=datetime.fromisoformat(row["l_created_at"]),
        )
        results.append((item, link))
    return results


def find_work_items_by_ref_exact(conn: sqlite3.Connection, ref: str) -> list[tuple[WorkItem, Link]]:
    """Find work items with links matching an exact entity_ref."""
    rows = conn.execute(
        """SELECT w.*, l.entity_type as l_entity_type, l.entity_url as l_entity_url,
                  l.entity_repo as l_entity_repo, l.entity_ref as l_entity_ref,
                  l.relationship as l_relationship, l.notes as l_notes,
                  l.created_at as l_created_at, l.work_item_id as l_work_item_id
           FROM work_items w
           JOIN links l ON l.work_item_id = w.id
           WHERE l.entity_ref = ?""",
        (ref,),
    ).fetchall()
    results = []
    for row in rows:
        item = _row_to_work_item(row)
        link = Link(
            work_item_id=row["l_work_item_id"],
            entity_type=row["l_entity_type"],
            entity_url=row["l_entity_url"],
            entity_repo=row["l_entity_repo"],
            entity_ref=row["l_entity_ref"],
            relationship=row["l_relationship"],
            notes=row["l_notes"],
            created_at=datetime.fromisoformat(row["l_created_at"]),
        )
        results.append((item, link))
    return results


def find_work_items_by_ref(conn: sqlite3.Connection, ref_pattern: str) -> list[tuple[WorkItem, Link]]:
    """Find work items with links matching a partial entity_ref (LIKE search)."""
    rows = conn.execute(
        """SELECT w.*, l.entity_type as l_entity_type, l.entity_url as l_entity_url,
                  l.entity_repo as l_entity_repo, l.entity_ref as l_entity_ref,
                  l.relationship as l_relationship, l.notes as l_notes,
                  l.created_at as l_created_at, l.work_item_id as l_work_item_id
           FROM work_items w
           JOIN links l ON l.work_item_id = w.id
           WHERE l.entity_ref LIKE ?""",
        (f"%{ref_pattern}%",),
    ).fetchall()
    results = []
    for row in rows:
        item = _row_to_work_item(row)
        link = Link(
            work_item_id=row["l_work_item_id"],
            entity_type=row["l_entity_type"],
            entity_url=row["l_entity_url"],
            entity_repo=row["l_entity_repo"],
            entity_ref=row["l_entity_ref"],
            relationship=row["l_relationship"],
            notes=row["l_notes"],
            created_at=datetime.fromisoformat(row["l_created_at"]),
        )
        results.append((item, link))
    return results


def find_reverse_links(conn: sqlite3.Connection, work_item_id: str) -> list[tuple[WorkItem, Link]]:
    """Find other work items that link to this one via work_item:// URLs."""
    target_url = f"work_item://{work_item_id}"
    return find_work_items_by_url(conn, target_url)


def _row_to_work_item(row: sqlite3.Row) -> WorkItem:
    return WorkItem(
        id=row["id"],
        title=row["title"],
        status=WorkItemStatus(row["status"]),
        description=row["description"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_link(row: sqlite3.Row) -> Link:
    return Link(
        work_item_id=row["work_item_id"],
        entity_type=row["entity_type"],
        entity_url=row["entity_url"],
        entity_repo=row["entity_repo"],
        entity_ref=row["entity_ref"],
        relationship=row["relationship"],
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
