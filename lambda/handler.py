"""
handler.py
----------
AWS Lambda entry point for the Maintainer Burnout Guard agent.
Triggered nightly by an EventBridge scheduled rule.

Pipeline:
  1. load_config()       — batch SSM fetch
  2. fetch_issues()      — per repo, paginated GitHub REST API
  3. analyze_all()       — parallel Bedrock Nova Lite analysis
  4. draft_response()    — sequential, flagged issues only
  5. build_digest()      — HTML + plain-text assembly
  6. send_digest()       — SES delivery

On any unhandled exception: logs a structured JSON error record
then re-raises so Lambda marks the invocation failed (enabling
EventBridge retry and surfacing the error in CloudWatch).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from lambda.config import AppConfig, load_config
from lambda.github.fetch_issues import GitHubError, GitHubIssue, fetch_issues
from lambda.analysis.analyze_issue import AnalysisResult, analyze_issue
from lambda.response.draft_response import draft_response
from lambda.digest.build_digest import FlaggedItem, build_digest, build_digest_text
from lambda.email.send_digest import send_digest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Maximum parallel Bedrock workers for issue analysis
_MAX_ANALYSIS_WORKERS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_step(step: str, detail: str, elapsed_ms: float) -> None:
    """Emit a structured JSON log line for each pipeline step."""
    logger.info(json.dumps({
        "step": step,
        "detail": detail,
        "elapsed_ms": round(elapsed_ms, 1),
    }))


def _fetch_all_issues(config: AppConfig, since: datetime) -> List[GitHubIssue]:
    """Fetch issues from all configured repos, collecting errors without aborting."""
    all_issues: List[GitHubIssue] = []
    for repo in config.repos:
        try:
            issues = fetch_issues(repo, since, config.github_token)
            all_issues.extend(issues)
        except GitHubError as exc:
            # Log and skip — one bad repo shouldn't kill the whole run
            logger.error(
                json.dumps({
                    "step": "fetch_issues",
                    "repo": repo,
                    "error": str(exc),
                    "status": exc.status,
                })
            )
    return all_issues


def _analyze_all(
    issues: List[GitHubIssue],
    config: AppConfig,
) -> List[Tuple[GitHubIssue, AnalysisResult]]:
    """
    Run Bedrock analysis for all issues in parallel.
    Uses ThreadPoolExecutor — Bedrock calls are I/O-bound.
    Returns only flagged items.
    """
    flagged: List[Tuple[GitHubIssue, AnalysisResult]] = []

    with ThreadPoolExecutor(max_workers=_MAX_ANALYSIS_WORKERS) as pool:
        future_to_issue = {
            pool.submit(analyze_issue, issue, config): issue
            for issue in issues
        }
        for future in as_completed(future_to_issue):
            issue = future_to_issue[future]
            try:
                result = future.result()
            except Exception as exc:   # noqa: BLE001
                logger.warning(
                    "[handler] Unexpected error analyzing issue #%d in %s: %s",
                    issue.number, issue.repo, exc,
                )
                continue
            if result.flagged:
                flagged.append((issue, result))

    # Sort deterministically for consistent digest ordering
    flagged.sort(key=lambda x: x[1].severity, reverse=True)
    return flagged


def _draft_all(
    flagged: List[Tuple[GitHubIssue, AnalysisResult]],
    config: AppConfig,
) -> List[FlaggedItem]:
    """Draft responses for all flagged issues sequentially."""
    items: List[FlaggedItem] = []
    for issue, analysis in flagged:
        try:
            draft = draft_response(issue, analysis, config)
        except Exception as exc:   # noqa: BLE001
            logger.warning(
                "[handler] Failed to draft response for issue #%d in %s: %s",
                issue.number, issue.repo, exc,
            )
            draft = "(Draft unavailable — please write a manual response)"
        items.append(FlaggedItem(issue=issue, analysis=analysis, draft=draft))
    return items


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context: object) -> None:  # type: ignore[type-arg]
    """
    EventBridge scheduled event handler.
    `context` is the Lambda context object (aws_request_id used for error logs).
    """
    request_id = getattr(context, "aws_request_id", "local")
    run_start = time.monotonic()
    run_date = datetime.now(tz=timezone.utc)

    logger.info(json.dumps({
        "step": "start",
        "request_id": request_id,
        "run_date": run_date.isoformat(),
    }))

    try:
        # ── 1. Config ────────────────────────────────────────────────────────
        t0 = time.monotonic()
        config = load_config()
        _log_step("load_config", f"repos={config.repos}", (time.monotonic() - t0) * 1000)

        # ── 2. Fetch issues ──────────────────────────────────────────────────
        t0 = time.monotonic()
        since = run_date - timedelta(hours=config.lookback_hours)
        all_issues = _fetch_all_issues(config, since)
        _log_step(
            "fetch_issues",
            f"total={len(all_issues)} repos={len(config.repos)}",
            (time.monotonic() - t0) * 1000,
        )

        # ── 3. Analyze in parallel ───────────────────────────────────────────
        t0 = time.monotonic()
        flagged_pairs = _analyze_all(all_issues, config)
        _log_step(
            "analyze_all",
            f"reviewed={len(all_issues)} flagged={len(flagged_pairs)}",
            (time.monotonic() - t0) * 1000,
        )

        # ── 4. Draft responses ───────────────────────────────────────────────
        t0 = time.monotonic()
        flagged_items = _draft_all(flagged_pairs, config)
        _log_step(
            "draft_all",
            f"drafted={len(flagged_items)}",
            (time.monotonic() - t0) * 1000,
        )

        # ── 5. Build digest ──────────────────────────────────────────────────
        t0 = time.monotonic()
        html_body = build_digest(flagged_items, len(all_issues), config.repos, run_date)
        text_body = build_digest_text(flagged_items, len(all_issues), run_date)
        _log_step("build_digest", f"html_bytes={len(html_body)}", (time.monotonic() - t0) * 1000)

        # ── 6. Send email ────────────────────────────────────────────────────
        t0 = time.monotonic()
        send_digest(html_body, text_body, len(flagged_items), run_date, config)
        _log_step("send_digest", f"to={config.ses_to}", (time.monotonic() - t0) * 1000)

        total_ms = (time.monotonic() - run_start) * 1000
        logger.info(json.dumps({
            "step": "complete",
            "request_id": request_id,
            "total_ms": round(total_ms, 1),
            "reviewed": len(all_issues),
            "flagged": len(flagged_items),
        }))

    except Exception as exc:
        logger.error(json.dumps({
            "step": "fatal_error",
            "request_id": request_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - run_start) * 1000, 1),
        }))
        raise
