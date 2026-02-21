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


class WorkItemStatus(enum.Enum):
    """Work item lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class EntityType(enum.Enum):
    """Type of entity linked to a work item."""

    PR = "pr"
    ISSUE = "issue"
    NOTIFICATION = "notification"
    CHECK_SUITE = "check_suite"
    WORK_ITEM = "work_item"


class Relationship(enum.Enum):
    """How an entity relates to a work item."""

    TRACKS = "tracks"
    BLOCKED_BY = "blocked_by"
    IMPLEMENTS = "implements"
    RELATED = "related"


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


@dataclass
class WorkItem:
    """A named work stream with linked entities."""

    id: str
    title: str
    status: WorkItemStatus = WorkItemStatus.ACTIVE
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    link_count: int = 0  # populated by list queries


@dataclass
class Link:
    """A link between a work item and an external entity."""

    work_item_id: str
    entity_type: str
    entity_url: str
    entity_repo: str = ""
    entity_ref: str = ""
    relationship: str = "related"
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)
