"""Async gh CLI subprocess wrapper for GitHub notifications."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime

from gh_notify.config import gh_config_dir, gh_path
from gh_notify.models import Notification


def _build_env() -> dict[str, str]:
    """Build env dict with GH_CONFIG_DIR and PATH."""
    env = os.environ.copy()
    env["GH_CONFIG_DIR"] = gh_config_dir()
    return env


async def _run_gh(*args: str) -> str:
    """Run a gh CLI command and return stdout. Raises on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        gh_path(),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_build_env(),
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed (exit {proc.returncode}): {stderr.decode().strip()}")
    return stdout.decode()


def _parse_notification(raw: dict) -> Notification:
    """Parse a single notification JSON object from the GitHub API."""
    subject = raw.get("subject", {})
    repo = raw.get("repository", {}).get("full_name", "")

    last_read = raw.get("last_read_at")
    last_read_dt = datetime.fromisoformat(last_read) if last_read else None

    return Notification(
        thread_id=raw["id"],
        reason=raw.get("reason", "unknown"),
        repo=repo,
        subject_title=subject.get("title", ""),
        subject_type=subject.get("type", ""),
        subject_url=subject.get("url", "") or "",
        latest_comment_url=subject.get("latest_comment_url", "") or "",
        unread=raw.get("unread", True),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
        last_read_at=last_read_dt,
    )


async def fetch_notifications() -> list[Notification]:
    """Fetch all notifications via gh api --paginate."""
    output = await _run_gh("api", "/notifications", "--paginate")
    if not output.strip():
        return []
    raw_list = json.loads(output)
    return [_parse_notification(item) for item in raw_list]


async def mark_thread_read(thread_id: str) -> None:
    """Mark a single notification thread as read on GitHub."""
    await _run_gh("api", f"/notifications/threads/{thread_id}", "--method", "PATCH")
