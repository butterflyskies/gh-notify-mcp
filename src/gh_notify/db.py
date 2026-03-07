"""SQLite state layer for notification triage."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from gh_notify.config import db_path
from gh_notify.models import Notification, Status

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS notifications (
    thread_id          TEXT PRIMARY KEY,
    reason             TEXT NOT NULL,
    repo               TEXT NOT NULL,
    subject_title      TEXT NOT NULL,
    subject_type       TEXT NOT NULL,
    subject_url        TEXT NOT NULL DEFAULT '',
    latest_comment_url TEXT NOT NULL DEFAULT '',
    unread             BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at         TIMESTAMP NOT NULL,
    last_read_at       TIMESTAMP,
    status             TEXT NOT NULL DEFAULT 'new',
    notes              TEXT NOT NULL DEFAULT '',
    status_changed_at  TIMESTAMP,
    first_seen_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_status ON notifications(status);
CREATE INDEX IF NOT EXISTS idx_repo ON notifications(repo);

CREATE TABLE IF NOT EXISTS work_items (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_item_id  TEXT NOT NULL REFERENCES work_items(id),
    entity_type   TEXT NOT NULL,
    entity_url    TEXT NOT NULL,
    entity_repo   TEXT NOT NULL DEFAULT '',
    entity_ref    TEXT NOT NULL DEFAULT '',
    relationship  TEXT NOT NULL DEFAULT 'related',
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMP NOT NULL,
    UNIQUE(work_item_id, entity_url)
);

CREATE INDEX IF NOT EXISTS idx_links_work_item ON links(work_item_id);
CREATE INDEX IF NOT EXISTS idx_links_entity_url ON links(entity_url);
CREATE INDEX IF NOT EXISTS idx_links_entity_ref ON links(entity_ref);
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
"""


def _connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or str(db_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _row_to_notification(row: sqlite3.Row) -> Notification:
    return Notification(
        thread_id=row["thread_id"],
        reason=row["reason"],
        repo=row["repo"],
        subject_title=row["subject_title"],
        subject_type=row["subject_type"],
        subject_url=row["subject_url"],
        latest_comment_url=row["latest_comment_url"],
        unread=bool(row["unread"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_read_at=datetime.fromisoformat(row["last_read_at"]) if row["last_read_at"] else None,
        status=Status(row["status"]),
        notes=row["notes"],
        status_changed_at=(
            datetime.fromisoformat(row["status_changed_at"]) if row["status_changed_at"] else None
        ),
        first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
    )


def upsert(conn: sqlite3.Connection, notifications: list[Notification]) -> dict[str, int]:
    """Upsert notifications. New threads get status='new'; existing threads keep their status."""
    new_count = 0
    updated_count = 0

    for n in notifications:
        existing = conn.execute(
            "SELECT thread_id, status FROM notifications WHERE thread_id = ?",
            (n.thread_id,),
        ).fetchone()

        if existing is None:
            conn.execute(
                """INSERT INTO notifications
                   (thread_id, reason, repo, subject_title, subject_type, subject_url,
                    latest_comment_url, unread, updated_at, last_read_at, status, notes,
                    status_changed_at, first_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    n.thread_id,
                    n.reason,
                    n.repo,
                    n.subject_title,
                    n.subject_type,
                    n.subject_url,
                    n.latest_comment_url,
                    n.unread,
                    n.updated_at.isoformat(),
                    n.last_read_at.isoformat() if n.last_read_at else None,
                    Status.NEW.value,
                    "",
                    None,
                    datetime.now().isoformat(),
                ),
            )
            new_count += 1
        else:
            conn.execute(
                """UPDATE notifications SET
                   reason = ?, repo = ?, subject_title = ?, subject_type = ?,
                   subject_url = ?, latest_comment_url = ?, unread = ?,
                   updated_at = ?, last_read_at = ?
                   WHERE thread_id = ?""",
                (
                    n.reason,
                    n.repo,
                    n.subject_title,
                    n.subject_type,
                    n.subject_url,
                    n.latest_comment_url,
                    n.unread,
                    n.updated_at.isoformat(),
                    n.last_read_at.isoformat() if n.last_read_at else None,
                    n.thread_id,
                ),
            )
            updated_count += 1

    conn.commit()
    return {"new": new_count, "updated": updated_count}


def list_actionable(
    conn: sqlite3.Connection,
    *,
    repo: str | None = None,
    reason: str | None = None,
    subject_type: str | None = None,
) -> list[Notification]:
    """Return notifications with status 'new' or 'triaged', optionally filtered."""
    query = "SELECT * FROM notifications WHERE status IN ('new', 'triaged')"
    params: list[Any] = []

    if repo:
        query += " AND repo = ?"
        params.append(repo)
    if reason:
        query += " AND reason = ?"
        params.append(reason)
    if subject_type:
        query += " AND subject_type = ?"
        params.append(subject_type)

    query += " ORDER BY updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    return [_row_to_notification(r) for r in rows]


def set_status(
    conn: sqlite3.Connection,
    thread_id: str,
    status: Status,
    notes: str | None = None,
) -> bool:
    """Set the triage status of a notification. Returns False if thread_id not found."""
    existing = conn.execute(
        "SELECT thread_id FROM notifications WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if existing is None:
        return False

    now = datetime.now().isoformat()
    if notes is not None:
        conn.execute(
            "UPDATE notifications SET status = ?, notes = ?, status_changed_at = ? WHERE thread_id = ?",
            (status.value, notes, now, thread_id),
        )
    else:
        conn.execute(
            "UPDATE notifications SET status = ?, status_changed_at = ? WHERE thread_id = ?",
            (status.value, now, thread_id),
        )

    conn.commit()
    return True


def get_thread(conn: sqlite3.Connection, thread_id: str) -> Notification | None:
    """Get a single notification by thread_id."""
    row = conn.execute(
        "SELECT * FROM notifications WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    return _row_to_notification(row) if row else None


def get_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Summary counts by status, repo, and reason."""
    by_status: dict[str, int] = {}
    for row in conn.execute("SELECT status, COUNT(*) as cnt FROM notifications GROUP BY status"):
        by_status[row["status"]] = row["cnt"]

    by_repo: dict[str, int] = {}
    for row in conn.execute("SELECT repo, COUNT(*) as cnt FROM notifications GROUP BY repo ORDER BY cnt DESC"):
        by_repo[row["repo"]] = row["cnt"]

    by_reason: dict[str, int] = {}
    for row in conn.execute("SELECT reason, COUNT(*) as cnt FROM notifications GROUP BY reason ORDER BY cnt DESC"):
        by_reason[row["reason"]] = row["cnt"]

    total = conn.execute("SELECT COUNT(*) as cnt FROM notifications").fetchone()["cnt"]

    return {
        "total": total,
        "by_status": by_status,
        "by_repo": by_repo,
        "by_reason": by_reason,
    }


def find_notifications_by_repo(
    conn: sqlite3.Connection,
    repo: str,
    number: int | None = None,
) -> list[Notification]:
    """Find notifications matching a repo and optional entity number/ID.

    Cross-references subject_url which contains API URLs like
    https://api.github.com/repos/owner/repo/pulls/123.
    Matches any API path ending in the number (pulls, issues, check-suites, etc.).
    """
    if number is not None:
        # Match subject_url ending with /<number> after any API path segment
        rows = conn.execute(
            """SELECT * FROM notifications
               WHERE repo = ? AND subject_url LIKE ?
               ORDER BY updated_at DESC""",
            (repo, f"%/{number}"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE repo = ? ORDER BY updated_at DESC",
            (repo,),
        ).fetchall()
    return [_row_to_notification(r) for r in rows]


def connect(path: str | None = None) -> sqlite3.Connection:
    """Public connection factory."""
    return _connect(path)
