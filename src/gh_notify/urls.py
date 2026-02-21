"""GitHub URL parsing, normalization, and short-ref expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedGitHubURL:
    """Parsed GitHub entity URL."""

    entity_type: str  # pr, issue, check_suite, discussion, commit, repo
    owner: str
    repo: str
    number: int | None  # None for repo-level URLs
    full_repo: str  # "owner/repo"
    short_ref: str  # "owner/repo#123" or "owner/repo" for repo-level
    canonical_url: str  # normalized https://github.com/... URL


# Regex for github.com web URLs:
# /owner/repo/pull/123, /owner/repo/issues/123, etc.
_WEB_RE = re.compile(
    r"https?://github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?P<kind>pull|pulls|issue|issues|discussions|commit|check_suite|actions/runs)/(?P<number>[^/?#]+))?"
)

# Regex for api.github.com URLs:
# /repos/owner/repo/pulls/123, /repos/owner/repo/issues/123, etc.
_API_RE = re.compile(
    r"https?://api\.github\.com/repos/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?P<kind>pulls|issues|commits|check-suites|check-runs|actions/runs)/(?P<number>[^/?#]+))?"
)

# Short ref: owner/repo#123
_SHORT_REF_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)#(?P<number>\d+)$"
)

_KIND_TO_TYPE = {
    "pull": "pr",
    "pulls": "pr",
    "issue": "issue",
    "issues": "issue",
    "discussions": "discussion",
    "commit": "commit",
    "commits": "commit",
    "check_suite": "check_suite",
    "check-suites": "check_suite",
    "check-runs": "check_suite",
    "actions/runs": "check_suite",
}

_TYPE_TO_WEB_PATH = {
    "pr": "pull",
    "issue": "issues",
    "discussion": "discussions",
    "commit": "commit",
    "check_suite": "actions/runs",
}


def parse_github_url(url: str) -> ParsedGitHubURL | None:
    """Parse a GitHub web or API URL into structured components.

    Handles both github.com and api.github.com URLs.
    Returns None if the URL doesn't match.
    """
    # Strip query params and fragments before matching
    clean_url = url.split("?")[0].split("#")[0]
    m = _WEB_RE.match(clean_url) or _API_RE.match(clean_url)
    if not m:
        return None

    owner = m.group("owner")
    repo = m.group("repo")
    kind = m.group("kind")
    number_str = m.group("number")
    full_repo = f"{owner}/{repo}"

    if kind and number_str:
        entity_type = _KIND_TO_TYPE.get(kind, "issue")
        try:
            number = int(number_str)
        except ValueError:
            # commit SHAs or other non-numeric identifiers
            number = None
        short_ref = f"{full_repo}#{number}" if number is not None else full_repo
        web_path = _TYPE_TO_WEB_PATH.get(entity_type, kind)
        canonical = f"https://github.com/{full_repo}/{web_path}/{number_str}"
    else:
        entity_type = "repo"
        number = None
        short_ref = full_repo
        canonical = f"https://github.com/{full_repo}"

    return ParsedGitHubURL(
        entity_type=entity_type,
        owner=owner,
        repo=repo,
        number=number,
        full_repo=full_repo,
        short_ref=short_ref,
        canonical_url=canonical,
    )


def parse_short_ref(ref: str) -> ParsedGitHubURL | None:
    """Parse 'owner/repo#123' into a ParsedGitHubURL.

    Returns None for ambiguous refs without owner (e.g. '#123' or 'repo#123').
    """
    m = _SHORT_REF_RE.match(ref.strip())
    if not m:
        return None

    owner = m.group("owner")
    repo = m.group("repo")
    number = int(m.group("number"))
    full_repo = f"{owner}/{repo}"

    # We can't distinguish PR from issue by short ref alone; default to issue
    return ParsedGitHubURL(
        entity_type="issue",
        owner=owner,
        repo=repo,
        number=number,
        full_repo=full_repo,
        short_ref=f"{full_repo}#{number}",
        canonical_url=f"https://github.com/{full_repo}/issues/{number}",
    )


def normalize_url(url: str) -> str:
    """Normalize a GitHub URL: strip fragments, query params, trailing subpaths.

    Converts API URLs to web URLs. Returns the canonical form.
    """
    parsed = parse_github_url(url)
    if parsed:
        return parsed.canonical_url
    # Not a recognized GitHub URL; strip fragment and query
    url = url.split("#")[0].split("?")[0].rstrip("/")
    return url


def detect_entity_type(url_or_ref: str) -> str | None:
    """Detect entity type from a URL, short ref, or work_item:// slug.

    Returns: 'pr', 'issue', 'check_suite', 'notification', 'work_item', 'repo', or None.
    """
    if url_or_ref.startswith("work_item://"):
        return "work_item"
    parsed = parse_github_url(url_or_ref) or parse_short_ref(url_or_ref)
    if parsed:
        return parsed.entity_type
    return None
