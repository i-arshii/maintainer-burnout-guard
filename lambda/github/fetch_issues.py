"""
github/fetch_issues.py
----------------------
Fetches newly opened GitHub issues from a repository via the REST API.
- Supports pagination (loops until empty page)
- Filters out pull requests (GitHub returns them mixed with issues)
- Respects rate limits: skips repo if fewer than 10 requests remain
- Raises GitHubError on non-200 responses
"""

from __future__ import annotations

import logging
import urllib.request
import urllib.error
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubError(Exception):
    """Raised when the GitHub API returns a non-200 status."""
    def __init__(self, status: int, message: str, repo: str):
        super().__init__(f"[GitHub:{repo}] HTTP {status}: {message}")
        self.status = status
        self.repo = repo


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    html_url: str
    author: str
    created_at: str
    repo: str          # injected: "owner/repo"


def fetch_issues(repo: str, since: datetime, token: str) -> List[GitHubIssue]:
    """
    Fetch all open issues created since `since` for a given repo.
    `since` must be timezone-aware (UTC).
    Returns a list of GitHubIssue, excluding pull requests.
    """
    issues: List[GitHubIssue] = []
    page = 1

    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    while True:
        params = urlencode({
            "state": "open",
            "since": since_iso,
            "per_page": 100,
            "page": page,
            "sort": "created",
            "direction": "desc",
        })
        url = f"{GITHUB_API_BASE}/repos/{repo}/issues?{params}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "maintainer-burnout-guard/1.0",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                # Rate limit check
                remaining = int(resp.headers.get("X-RateLimit-Remaining", 100))
                if remaining <= 10:
                    logger.warning(
                        "[github] Rate limit low (%d remaining) — skipping further pages for %s",
                        remaining, repo,
                    )
                    break

                raw = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise GitHubError(exc.code, body, repo) from exc

        if not raw:
            break  # no more pages

        for item in raw:
            # Skip pull requests — GitHub mixes them into the issues endpoint
            if "pull_request" in item:
                continue

            issues.append(GitHubIssue(
                number=item["number"],
                title=item.get("title", "(no title)"),
                body=item.get("body") or "(no description provided)",
                html_url=item["html_url"],
                author=item["user"]["login"],
                created_at=item["created_at"],
                repo=repo,
            ))

        # If we got fewer than 100 results, we're on the last page
        if len(raw) < 100:
            break

        page += 1

    logger.info("[github] Fetched %d issues from %s since %s", len(issues), repo, since_iso)
    return issues
