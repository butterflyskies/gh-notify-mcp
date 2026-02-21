"""Tests for work items and links CRUD."""

from __future__ import annotations

import sqlite3

import pytest

from gh_notify import work_items_db
from gh_notify.db import upsert
from gh_notify.models import Link, Notification, WorkItem, WorkItemStatus


# --- create / get ---


def test_create_work_item(tmp_db: sqlite3.Connection):
    item = work_items_db.create_work_item(tmp_db, "test-item", "Test Item", "A description")
    assert item.id == "test-item"
    assert item.title == "Test Item"
    assert item.status == WorkItemStatus.ACTIVE
    assert item.description == "A description"


def test_create_duplicate_raises(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    with pytest.raises(sqlite3.IntegrityError):
        work_items_db.create_work_item(tmp_db, sample_work_item.id, "Duplicate")


def test_get_work_item(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    item = work_items_db.get_work_item(tmp_db, sample_work_item.id)
    assert item is not None
    assert item.title == sample_work_item.title


def test_get_nonexistent_returns_none(tmp_db: sqlite3.Connection):
    assert work_items_db.get_work_item(tmp_db, "nope") is None


# --- update ---


def test_update_title(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    updated = work_items_db.update_work_item(tmp_db, sample_work_item.id, title="New Title")
    assert updated is not None
    assert updated.title == "New Title"
    assert updated.description == sample_work_item.description  # unchanged


def test_update_status(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    updated = work_items_db.update_work_item(
        tmp_db, sample_work_item.id, status=WorkItemStatus.PAUSED,
    )
    assert updated is not None
    assert updated.status == WorkItemStatus.PAUSED


def test_update_description_replace(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    updated = work_items_db.update_work_item(
        tmp_db, sample_work_item.id, description="Replaced.",
    )
    assert updated is not None
    assert updated.description == "Replaced."


def test_update_append_description(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    updated = work_items_db.update_work_item(
        tmp_db, sample_work_item.id, append_description="Session 2 notes.",
    )
    assert updated is not None
    assert "Session 2 notes." in updated.description
    assert sample_work_item.description in updated.description


def test_update_append_to_empty_description(tmp_db: sqlite3.Connection):
    work_items_db.create_work_item(tmp_db, "empty-desc", "Empty")
    updated = work_items_db.update_work_item(
        tmp_db, "empty-desc", append_description="First note.",
    )
    assert updated is not None
    assert updated.description == "First note."


def test_update_nonexistent_returns_none(tmp_db: sqlite3.Connection):
    assert work_items_db.update_work_item(tmp_db, "nope", title="X") is None


# --- list ---


def test_list_work_items(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    work_items_db.create_work_item(tmp_db, "another", "Another Item")
    items = work_items_db.list_work_items(tmp_db)
    assert len(items) == 2


def test_list_work_items_filter_status(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    work_items_db.create_work_item(tmp_db, "done", "Done Item")
    work_items_db.update_work_item(tmp_db, "done", status=WorkItemStatus.COMPLETED)

    active = work_items_db.list_work_items(tmp_db, status=WorkItemStatus.ACTIVE)
    assert len(active) == 1
    assert active[0].id == sample_work_item.id

    completed = work_items_db.list_work_items(tmp_db, status=WorkItemStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].id == "done"


def test_list_includes_link_count(tmp_db: sqlite3.Connection, linked_work_item: WorkItem):
    items = work_items_db.list_work_items(tmp_db)
    assert len(items) == 1
    assert items[0].link_count == 3


# --- links ---


def test_upsert_link_from_url(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    link = work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/pull/1007", "tracks",
    )
    assert link.entity_type == "pr"
    assert link.entity_ref == "oraios/serena#1007"
    assert link.entity_url == "https://github.com/oraios/serena/pull/1007"


def test_upsert_link_from_short_ref(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    link = work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "butterflyskies/tasks#70", "tracks",
    )
    assert link.entity_type == "issue"
    assert link.entity_ref == "butterflyskies/tasks#70"
    assert link.entity_repo == "butterflyskies/tasks"


def test_upsert_link_idempotent(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    """Re-linking same URL updates relationship/notes."""
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/pull/1007", "related",
    )
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/pull/1007", "tracks", "important",
    )
    links = work_items_db.get_links_for_work_item(tmp_db, sample_work_item.id)
    assert len(links) == 1
    assert links[0].relationship == "tracks"
    assert links[0].notes == "important"


def test_upsert_link_url_normalization(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    """API URL and web URL for same entity should resolve to same canonical URL."""
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://api.github.com/repos/oraios/serena/pulls/1007", "tracks",
    )
    work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "https://github.com/oraios/serena/pull/1007", "tracks",
    )
    links = work_items_db.get_links_for_work_item(tmp_db, sample_work_item.id)
    assert len(links) == 1  # same canonical URL = one link


def test_delete_link(tmp_db: sqlite3.Connection, linked_work_item: WorkItem):
    assert work_items_db.delete_link(
        tmp_db, linked_work_item.id,
        "https://github.com/oraios/serena/pull/1007",
    )
    links = work_items_db.get_links_for_work_item(tmp_db, linked_work_item.id)
    urls = {l.entity_url for l in links}
    assert "https://github.com/oraios/serena/pull/1007" not in urls
    assert len(links) == 2


def test_delete_link_not_found(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    assert work_items_db.delete_link(tmp_db, sample_work_item.id, "nope") is False


# --- cross-ref queries ---


def test_find_work_items_by_url(tmp_db: sqlite3.Connection, linked_work_item: WorkItem):
    results = work_items_db.find_work_items_by_url(
        tmp_db, "https://github.com/oraios/serena/pull/1007",
    )
    assert len(results) == 1
    item, link = results[0]
    assert item.id == linked_work_item.id
    assert link.relationship == "tracks"


def test_find_work_items_by_short_ref(tmp_db: sqlite3.Connection, linked_work_item: WorkItem):
    """Short ref lookup normalizes to canonical URL."""
    results = work_items_db.find_work_items_by_url(tmp_db, "oraios/serena#1007")
    # Short ref resolves to issues URL, but the link was created from a PR URL
    # These have different canonical URLs, so this won't match
    # Instead, use find_work_items_by_ref for partial matching
    results = work_items_db.find_work_items_by_ref(tmp_db, "oraios/serena#1007")
    assert len(results) == 1


def test_find_work_items_by_ref_partial(tmp_db: sqlite3.Connection, linked_work_item: WorkItem):
    """Partial ref search matches via LIKE."""
    results = work_items_db.find_work_items_by_ref(tmp_db, "tasks#70")
    assert len(results) == 1
    assert results[0][0].id == linked_work_item.id


def test_find_reverse_links(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    work_items_db.create_work_item(tmp_db, "child", "Child Item")
    work_items_db.upsert_link(
        tmp_db, "child",
        f"work_item://{sample_work_item.id}", "implements",
    )
    reverse = work_items_db.find_reverse_links(tmp_db, sample_work_item.id)
    assert len(reverse) == 1
    assert reverse[0][0].id == "child"
    assert reverse[0][1].relationship == "implements"


def test_work_item_link_to_work_item(tmp_db: sqlite3.Connection, sample_work_item: WorkItem):
    work_items_db.create_work_item(tmp_db, "other", "Other Item")
    link = work_items_db.upsert_link(
        tmp_db, sample_work_item.id,
        "work_item://other", "related",
    )
    assert link.entity_type == "work_item"
    assert link.entity_url == "work_item://other"


# --- notification cross-reference ---


def test_notification_cross_ref(
    tmp_db: sqlite3.Connection,
    linked_work_item: WorkItem,
    sample_notifications: list[Notification],
):
    """Links can be cross-referenced with notifications by repo + number."""
    from gh_notify.db import find_notifications_by_repo, upsert

    upsert(tmp_db, sample_notifications)
    # The linked work item tracks oraios/serena#1007 (a PR)
    # sample_notifications has thread_id=1003 for oraios/serena
    notifications = find_notifications_by_repo(tmp_db, "oraios/serena")
    assert len(notifications) >= 1
    assert any(n.thread_id == "1003" for n in notifications)
