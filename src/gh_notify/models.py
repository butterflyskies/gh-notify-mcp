"""Data models for GitHub notification triage."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class Status(enum.Enum):
    """Notification triage status."""

    NEW = "new"
    TRIAGED = "triaged"
    ACTED = "acted"
    DISMISSED = "dismissed"


@dataclass
class Notification:
    """A GitHub notification with triage state."""

    thread_id: str
    reason: str
    repo: str
    subject_title: str
    subject_type: str
    updated_at: datetime
    unread: bool = True
    subject_url: str = ""
    latest_comment_url: str = ""
    last_read_at: datetime | None = None
    status: Status = Status.NEW
    notes: str = ""
    status_changed_at: datetime | None = None
    first_seen_at: datetime = field(default_factory=datetime.now)
