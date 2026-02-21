"""Tests for the SQLite state layer."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from gh_notify.db import get_stats, get_thread, list_actionable, set_status, upsert
from gh_notify.models import Notification, Status


def test_upsert_new(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    result = upsert(tmp_db, sample_notifications)
    assert result["new"] == 4
    assert result["updated"] == 0

    # All should have status 'new'
    rows = tmp_db.execute("SELECT status FROM notifications").fetchall()
    assert all(r["status"] == "new" for r in rows)


def test_upsert_preserves_status(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)
    set_status(tmp_db, "1001", Status.TRIAGED, notes="reviewing")
    set_status(tmp_db, "1002", Status.DISMISSED)

    # Re-upsert same notifications
    result = upsert(tmp_db, sample_notifications)
    assert result["new"] == 0
    assert result["updated"] == 4

    # Statuses should be preserved
    t1 = get_thread(tmp_db, "1001")
    assert t1 is not None and t1.status is Status.TRIAGED
    t2 = get_thread(tmp_db, "1002")
    assert t2 is not None and t2.status is Status.DISMISSED


def test_upsert_updates_metadata(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)

    # Update the title of notification 1001
    updated = [
        Notification(
            thread_id="1001",
            reason="mention",
            repo="butterflyskies/serena",
            subject_title="UPDATED TITLE",
            subject_type="PullRequest",
            updated_at=datetime(2026, 2, 20, 12, 0, 0),
        )
    ]
    upsert(tmp_db, updated)

    t = get_thread(tmp_db, "1001")
    assert t is not None
    assert t.subject_title == "UPDATED TITLE"
    assert t.updated_at == datetime(2026, 2, 20, 12, 0, 0)


def test_list_actionable_returns_new_and_triaged(
    tmp_db: sqlite3.Connection, sample_notifications: list[Notification]
):
    upsert(tmp_db, sample_notifications)
    set_status(tmp_db, "1001", Status.TRIAGED)

    actionable = list_actionable(tmp_db)
    ids = {n.thread_id for n in actionable}
    assert "1001" in ids  # triaged
    assert "1002" in ids  # new
    assert "1003" in ids  # new
    assert "1004" in ids  # new


def test_list_actionable_excludes_acted_and_dismissed(
    tmp_db: sqlite3.Connection, sample_notifications: list[Notification]
):
    upsert(tmp_db, sample_notifications)
    set_status(tmp_db, "1001", Status.ACTED)
    set_status(tmp_db, "1002", Status.DISMISSED)

    actionable = list_actionable(tmp_db)
    ids = {n.thread_id for n in actionable}
    assert "1001" not in ids
    assert "1002" not in ids
    assert "1003" in ids
    assert "1004" in ids


def test_list_actionable_filters_by_repo(
    tmp_db: sqlite3.Connection, sample_notifications: list[Notification]
):
    upsert(tmp_db, sample_notifications)
    actionable = list_actionable(tmp_db, repo="oraios/serena")
    assert len(actionable) == 1
    assert actionable[0].thread_id == "1003"


def test_list_actionable_filters_by_reason(
    tmp_db: sqlite3.Connection, sample_notifications: list[Notification]
):
    upsert(tmp_db, sample_notifications)
    actionable = list_actionable(tmp_db, reason="ci_activity")
    assert len(actionable) == 1
    assert actionable[0].thread_id == "1002"


def test_list_actionable_filters_by_subject_type(
    tmp_db: sqlite3.Connection, sample_notifications: list[Notification]
):
    upsert(tmp_db, sample_notifications)
    actionable = list_actionable(tmp_db, subject_type="Issue")
    ids = {n.thread_id for n in actionable}
    assert ids == {"1003", "1004"}


def test_set_status_transitions(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)

    assert set_status(tmp_db, "1001", Status.TRIAGED)
    assert get_thread(tmp_db, "1001").status is Status.TRIAGED  # type: ignore[union-attr]

    assert set_status(tmp_db, "1001", Status.ACTED)
    assert get_thread(tmp_db, "1001").status is Status.ACTED  # type: ignore[union-attr]

    assert set_status(tmp_db, "1003", Status.DISMISSED)
    assert get_thread(tmp_db, "1003").status is Status.DISMISSED  # type: ignore[union-attr]


def test_set_status_nonexistent_returns_false(tmp_db: sqlite3.Connection):
    assert set_status(tmp_db, "nonexistent", Status.TRIAGED) is False


def test_set_status_with_notes(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)
    set_status(tmp_db, "1001", Status.TRIAGED, notes="Will review after lunch")

    t = get_thread(tmp_db, "1001")
    assert t is not None
    assert t.notes == "Will review after lunch"
    assert t.status_changed_at is not None


def test_get_stats_counts(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)
    set_status(tmp_db, "1001", Status.TRIAGED)
    set_status(tmp_db, "1002", Status.ACTED)

    stats = get_stats(tmp_db)
    assert stats["total"] == 4
    assert stats["by_status"]["new"] == 2
    assert stats["by_status"]["triaged"] == 1
    assert stats["by_status"]["acted"] == 1
    assert stats["by_repo"]["butterflyskies/serena"] == 2
    assert stats["by_reason"]["mention"] == 1


def test_get_thread_found(tmp_db: sqlite3.Connection, sample_notifications: list[Notification]):
    upsert(tmp_db, sample_notifications)
    t = get_thread(tmp_db, "1003")
    assert t is not None
    assert t.repo == "oraios/serena"


def test_get_thread_not_found(tmp_db: sqlite3.Connection):
    assert get_thread(tmp_db, "nonexistent") is None
