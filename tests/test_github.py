"""Tests for the gh CLI wrapper (mocked subprocess)."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from gh_notify.github import _parse_notification, fetch_notifications, mark_thread_read


SAMPLE_GH_OUTPUT = json.dumps([
    {
        "id": "5001",
        "reason": "mention",
        "unread": True,
        "updated_at": "2026-02-19T10:00:00Z",
        "last_read_at": "2026-02-19T09:00:00Z",
        "repository": {"full_name": "butterflyskies/serena"},
        "subject": {
            "title": "Add global memories",
            "type": "PullRequest",
            "url": "https://api.github.com/repos/butterflyskies/serena/pulls/42",
            "latest_comment_url": "https://api.github.com/repos/butterflyskies/serena/issues/comments/100",
        },
    },
    {
        "id": "5002",
        "reason": "ci_activity",
        "unread": False,
        "updated_at": "2026-02-18T08:00:00Z",
        "last_read_at": None,
        "repository": {"full_name": "oraios/serena"},
        "subject": {
            "title": "CI run failed",
            "type": "CheckSuite",
            "url": None,
            "latest_comment_url": None,
        },
    },
])


@pytest.mark.asyncio
async def test_fetch_notifications_parses_correctly():
    with patch("gh_notify.github._run_gh", new_callable=AsyncMock, return_value=SAMPLE_GH_OUTPUT):
        notifications = await fetch_notifications()

    assert len(notifications) == 2

    n1 = notifications[0]
    assert n1.thread_id == "5001"
    assert n1.reason == "mention"
    assert n1.repo == "butterflyskies/serena"
    assert n1.subject_title == "Add global memories"
    assert n1.subject_type == "PullRequest"
    assert n1.unread is True
    assert n1.last_read_at is not None

    n2 = notifications[1]
    assert n2.thread_id == "5002"
    assert n2.unread is False
    assert n2.last_read_at is None


@pytest.mark.asyncio
async def test_fetch_notifications_handles_empty_list():
    with patch("gh_notify.github._run_gh", new_callable=AsyncMock, return_value=""):
        notifications = await fetch_notifications()
    assert notifications == []


@pytest.mark.asyncio
async def test_fetch_notifications_raises_on_gh_error():
    async def mock_run(*args):
        raise RuntimeError("gh api /notifications failed (exit 1): auth required")

    with patch("gh_notify.github._run_gh", side_effect=mock_run):
        with pytest.raises(RuntimeError, match="auth required"):
            await fetch_notifications()


def test_parse_notification_handles_null_fields():
    raw = {
        "id": "9999",
        "reason": "assign",
        "unread": True,
        "updated_at": "2026-01-01T00:00:00Z",
        "last_read_at": None,
        "repository": {"full_name": "test/repo"},
        "subject": {
            "title": "Test issue",
            "type": "Issue",
            "url": None,
            "latest_comment_url": None,
        },
    }
    n = _parse_notification(raw)
    assert n.subject_url == ""
    assert n.latest_comment_url == ""
    assert n.last_read_at is None


@pytest.mark.asyncio
async def test_mark_thread_read_calls_correct_endpoint():
    mock_run = AsyncMock(return_value="")
    with patch("gh_notify.github._run_gh", mock_run):
        await mark_thread_read("12345")

    mock_run.assert_called_once_with(
        "api", "/notifications/threads/12345", "--method", "PATCH"
    )
