"""Shared fixtures for gh-notify tests."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from gh_notify.db import connect
from gh_notify.models import Notification, Status, WorkItem, WorkItemStatus
from gh_notify import work_items_db


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    """In-memory SQLite connection with schema applied."""
    conn = connect(str(tmp_path / "test.db"))
    yield conn
    conn.close()


@pytest.fixture
def sample_notifications() -> list[Notification]:
    """Realistic sample notifications for testing."""
    return [
        Notification(
            thread_id="1001",
            reason="mention",
            repo="butterflyskies/serena",
            subject_title="Add global memories support",
            subject_type="PullRequest",
            updated_at=datetime(2026, 2, 19, 10, 0, 0),
            subject_url="https://api.github.com/repos/butterflyskies/serena/pulls/42",
            latest_comment_url="https://api.github.com/repos/butterflyskies/serena/issues/comments/999",
        ),
        Notification(
            thread_id="1002",
            reason="ci_activity",
            repo="butterflyskies/serena",
            subject_title="CI: tests failing on main",
            subject_type="CheckSuite",
            updated_at=datetime(2026, 2, 19, 11, 0, 0),
        ),
        Notification(
            thread_id="1003",
            reason="author",
            repo="oraios/serena",
            subject_title="Fix memory persistence bug",
            subject_type="Issue",
            updated_at=datetime(2026, 2, 18, 9, 0, 0),
            last_read_at=datetime(2026, 2, 18, 8, 0, 0),
        ),
        Notification(
            thread_id="1004",
            reason="comment",
            repo="butterflyskies/tasks",
            subject_title="Implement notification triage",
            subject_type="Issue",
            updated_at=datetime(2026, 2, 20, 8, 0, 0),
        ),
    ]


@pytest.fixture
def sample_work_item(tmp_db: sqlite3.Connection) -> WorkItem:
    """A single work item in the database."""
    return work_items_db.create_work_item(
        tmp_db,
        id="serena-global-memories",
        title="Add global memories support to Serena",
        description="Track the global memories feature across PRs and issues.",
    )


@pytest.fixture
def linked_work_item(
    tmp_db: sqlite3.Connection,
    sample_work_item: WorkItem,
) -> WorkItem:
    """A work item with several linked entities."""
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/pull/1007", "tracks",
    )
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "butterflyskies/tasks#70", "tracks",
    )
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/issues/1055", "blocked_by",
    )
    # Refresh to get updated timestamp
    return work_items_db.get_work_item(tmp_db, sample_work_item.id)  # type: ignore[return-value]
