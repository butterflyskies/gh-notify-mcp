"""Tests for GitHub URL parsing and normalization."""

from __future__ import annotations

from gh_notify.urls import (
    ParsedGitHubURL,
    detect_entity_type,
    normalize_url,
    parse_github_url,
    parse_short_ref,
)


# --- parse_github_url ---


def test_parse_web_pr_url():
    result = parse_github_url("https://github.com/oraios/serena/pull/1007")
    assert result is not None
    assert result.entity_type == "pr"
    assert result.owner == "oraios"
    assert result.repo == "serena"
    assert result.number == 1007
    assert result.full_repo == "oraios/serena"
    assert result.short_ref == "oraios/serena#1007"
    assert result.canonical_url == "https://github.com/oraios/serena/pull/1007"


def test_parse_web_issue_url():
    result = parse_github_url("https://github.com/butterflyskies/tasks/issues/70")
    assert result is not None
    assert result.entity_type == "issue"
    assert result.number == 70
    assert result.short_ref == "butterflyskies/tasks#70"


def test_parse_web_pr_with_subpath():
    """PR URL with /files or /commits subpath should normalize to base PR."""
    result = parse_github_url("https://github.com/oraios/serena/pull/1007/files")
    assert result is not None
    assert result.entity_type == "pr"
    assert result.number == 1007
    assert result.canonical_url == "https://github.com/oraios/serena/pull/1007"


def test_parse_api_pulls_url():
    result = parse_github_url("https://api.github.com/repos/oraios/serena/pulls/1007")
    assert result is not None
    assert result.entity_type == "pr"
    assert result.number == 1007
    assert result.canonical_url == "https://github.com/oraios/serena/pull/1007"


def test_parse_api_issues_url():
    result = parse_github_url("https://api.github.com/repos/butterflyskies/tasks/issues/70")
    assert result is not None
    assert result.entity_type == "issue"
    assert result.number == 70
    assert result.canonical_url == "https://github.com/butterflyskies/tasks/issues/70"


def test_parse_repo_url():
    result = parse_github_url("https://github.com/butterflyskies/serena")
    assert result is not None
    assert result.entity_type == "repo"
    assert result.number is None
    assert result.short_ref == "butterflyskies/serena"
    assert result.canonical_url == "https://github.com/butterflyskies/serena"


def test_parse_actions_run_url():
    result = parse_github_url("https://github.com/oraios/serena/actions/runs/12345")
    assert result is not None
    assert result.entity_type == "check_suite"
    assert result.number == 12345


def test_parse_non_github_url_returns_none():
    assert parse_github_url("https://example.com/foo/bar") is None


def test_parse_empty_string_returns_none():
    assert parse_github_url("") is None


# --- parse_short_ref ---


def test_parse_short_ref_valid():
    result = parse_short_ref("oraios/serena#1007")
    assert result is not None
    assert result.owner == "oraios"
    assert result.repo == "serena"
    assert result.number == 1007
    assert result.full_repo == "oraios/serena"
    assert result.short_ref == "oraios/serena#1007"


def test_parse_short_ref_with_dots_and_hyphens():
    result = parse_short_ref("my-org/my.repo#42")
    assert result is not None
    assert result.full_repo == "my-org/my.repo"
    assert result.number == 42


def test_parse_short_ref_bare_number_returns_none():
    """Ambiguous refs without owner should return None."""
    assert parse_short_ref("#123") is None


def test_parse_short_ref_no_owner_returns_none():
    assert parse_short_ref("repo#123") is None


def test_parse_short_ref_whitespace_stripped():
    result = parse_short_ref("  oraios/serena#1007  ")
    assert result is not None
    assert result.number == 1007


# --- normalize_url ---


def test_normalize_strips_query_and_fragment():
    url = "https://github.com/oraios/serena/pull/1007?diff=unified#discussion_r123"
    assert normalize_url(url) == "https://github.com/oraios/serena/pull/1007"


def test_normalize_api_to_web():
    url = "https://api.github.com/repos/oraios/serena/pulls/1007"
    assert normalize_url(url) == "https://github.com/oraios/serena/pull/1007"


def test_normalize_non_github_url():
    url = "https://example.com/page?q=1#section"
    assert normalize_url(url) == "https://example.com/page"


# --- detect_entity_type ---


def test_detect_work_item_url():
    assert detect_entity_type("work_item://serena-global-memories") == "work_item"


def test_detect_pr_from_url():
    assert detect_entity_type("https://github.com/oraios/serena/pull/1007") == "pr"


def test_detect_issue_from_short_ref():
    assert detect_entity_type("butterflyskies/tasks#70") == "issue"


def test_detect_unknown_returns_none():
    assert detect_entity_type("random-string") is None
