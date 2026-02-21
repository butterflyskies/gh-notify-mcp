"""Tests for models.py."""

from datetime import datetime

from gh_notify.models import Notification, Status


def test_status_enum_values():
    assert Status.NEW.value == "new"
    assert Status.TRIAGED.value == "triaged"
    assert Status.ACTED.value == "acted"
    assert Status.DISMISSED.value == "dismissed"


def test_status_round_trip():
    for s in Status:
        assert Status(s.value) is s


def test_notification_defaults():
    n = Notification(
        thread_id="123",
        reason="mention",
        repo="foo/bar",
        subject_title="Test",
        subject_type="Issue",
        updated_at=datetime(2026, 1, 1),
    )
    assert n.unread is True
    assert n.subject_url == ""
    assert n.latest_comment_url == ""
    assert n.last_read_at is None
    assert n.status is Status.NEW
    assert n.notes == ""
    assert n.status_changed_at is None
    assert isinstance(n.first_seen_at, datetime)
