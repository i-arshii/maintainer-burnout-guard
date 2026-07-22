"""
digest/build_digest.py
-----------------------
Assembles the nightly HTML email digest from flagged issues and their
AI-drafted reply templates. Also produces a plain-text fallback.

Digest sections:
  - Header: run date, repos monitored, total reviewed, total flagged
  - Per flagged issue (sorted severity DESC): title, link, badge,
    flag reasons, copy-ready drafted reply
  - Footer: disclaimer
  - All-clear variant when no issues were flagged
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import List

from src.github.fetch_issues import GitHubIssue
from src.analysis.analyze_issue import AnalysisResult

# Severity badge colours
_BADGE_STYLES = {
    3: ("SEV-3", "#dc2626", "#fef2f2"),   # red
    2: ("SEV-2", "#d97706", "#fffbeb"),   # orange
    1: ("SEV-1", "#ca8a04", "#fefce8"),   # yellow
}


@dataclass
class FlaggedItem:
    issue: GitHubIssue
    analysis: AnalysisResult
    draft: str


# ---------------------------------------------------------------------------
# HTML digest
# ---------------------------------------------------------------------------

def build_digest(
    flagged: List[FlaggedItem],
    total_reviewed: int,
    repos: List[str],
    run_date: datetime,
) -> str:
    """Return a full HTML email body string."""

    date_str = run_date.strftime("%B %d, %Y")
    repos_str = ", ".join(repos)
    flagged_sorted = sorted(flagged, key=lambda x: x.analysis.severity, reverse=True)

    sections = [_html_header(date_str, repos_str, total_reviewed, len(flagged))]

    if not flagged_sorted:
        sections.append(_html_all_clear(total_reviewed))
    else:
        for item in flagged_sorted:
            sections.append(_html_issue_card(item))

    sections.append(_html_footer())

    return "\n".join(sections)


def _html_header(date_str: str, repos_str: str, total: int, flagged: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Burnout Guard Digest</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
             background: #f9fafb; margin: 0; padding: 24px;">
  <div style="max-width: 680px; margin: 0 auto;">

    <!-- Header -->
    <div style="background: #1e293b; border-radius: 12px 12px 0 0; padding: 24px 32px;">
      <h1 style="color: #f1f5f9; margin: 0; font-size: 22px;">
        🛡️ Burnout Guard
      </h1>
      <p style="color: #94a3b8; margin: 8px 0 0; font-size: 14px;">{date_str}</p>
    </div>

    <!-- Stats bar -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0; padding: 16px 32px;
                display: flex; gap: 32px;">
      <div>
        <span style="font-size: 12px; color: #64748b; text-transform: uppercase;
                     letter-spacing: 0.05em;">Repos monitored</span>
        <p style="margin: 4px 0 0; font-size: 14px; color: #1e293b;">{html.escape(repos_str)}</p>
      </div>
      <div>
        <span style="font-size: 12px; color: #64748b; text-transform: uppercase;
                     letter-spacing: 0.05em;">Issues reviewed</span>
        <p style="margin: 4px 0 0; font-size: 24px; font-weight: 700;
                  color: #1e293b;">{total}</p>
      </div>
      <div>
        <span style="font-size: 12px; color: #64748b; text-transform: uppercase;
                     letter-spacing: 0.05em;">Flagged</span>
        <p style="margin: 4px 0 0; font-size: 24px; font-weight: 700;
                  color: {'#dc2626' if flagged > 0 else '#16a34a'};">{flagged}</p>
      </div>
    </div>"""


def _html_all_clear(total: int) -> str:
    return f"""
    <!-- All clear -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0;
                border-top: none; padding: 48px 32px; text-align: center;">
      <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
      <h2 style="color: #16a34a; margin: 0 0 8px;">All clear</h2>
      <p style="color: #64748b; margin: 0;">
        {total} issue{'s' if total != 1 else ''} reviewed &mdash; none needed attention.
      </p>
    </div>"""


def _html_issue_card(item: FlaggedItem) -> str:
    issue = item.issue
    analysis = item.analysis
    severity = analysis.severity if analysis.severity in (1, 2, 3) else 1
    badge_label, badge_color, badge_bg = _BADGE_STYLES[severity]

    reasons_html = "".join(
        f"<li style='margin: 4px 0; color: #475569;'>{html.escape(r)}</li>"
        for r in analysis.reasons
    ) or "<li style='color: #475569;'>No specific reasons captured.</li>"

    draft_escaped = html.escape(item.draft)

    return f"""
    <!-- Issue card: #{issue.number} -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-top: none;
                padding: 24px 32px;">
      <div style="display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px;">
        <span style="background: {badge_bg}; color: {badge_color};
                     border: 1px solid {badge_color}; border-radius: 4px;
                     padding: 2px 8px; font-size: 11px; font-weight: 700;
                     white-space: nowrap;">{badge_label}</span>
        <div>
          <h3 style="margin: 0; font-size: 16px; color: #1e293b;">
            Issue #{issue.number}: {html.escape(issue.title)}
          </h3>
          <p style="margin: 4px 0 0; font-size: 13px; color: #64748b;">
            {html.escape(issue.repo)} &nbsp;|&nbsp;
            <a href="{html.escape(issue.html_url)}" style="color: #3b82f6;">
              View on GitHub →
            </a>
          </p>
        </div>
      </div>

      <div style="margin-bottom: 16px;">
        <p style="font-size: 12px; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.05em; color: #64748b; margin: 0 0 6px;">
          Flagged for
        </p>
        <ul style="margin: 0; padding-left: 20px;">
          {reasons_html}
        </ul>
      </div>

      <div>
        <p style="font-size: 12px; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 0.05em; color: #64748b; margin: 0 0 6px;">
          Suggested reply &mdash; copy and review before posting
        </p>
        <pre style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
                    padding: 16px; font-size: 13px; line-height: 1.6;
                    white-space: pre-wrap; word-break: break-word;
                    color: #334155; margin: 0;">{draft_escaped}</pre>
      </div>
    </div>"""


def _html_footer() -> str:
    return """
    <!-- Footer -->
    <div style="background: #f1f5f9; border: 1px solid #e2e8f0; border-top: none;
                border-radius: 0 0 12px 12px; padding: 16px 32px; text-align: center;">
      <p style="font-size: 12px; color: #94a3b8; margin: 0;">
        These are AI-drafted suggestions. Review carefully before posting to GitHub.
        <br>Burnout Guard &mdash; powered by AWS Bedrock &amp; Amazon Nova Lite
      </p>
    </div>

  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Plain-text fallback
# ---------------------------------------------------------------------------

def build_digest_text(
    flagged: List[FlaggedItem],
    total_reviewed: int,
    run_date: datetime,
) -> str:
    """Return a plain-text version of the digest for email clients that skip HTML."""

    date_str = run_date.strftime("%Y-%m-%d")
    lines: List[str] = [
        "=" * 60,
        f"BURNOUT GUARD DIGEST — {date_str}",
        "=" * 60,
        f"Issues reviewed : {total_reviewed}",
        f"Issues flagged  : {len(flagged)}",
        "",
    ]

    if not flagged:
        lines += ["✅ All clear — no issues needed attention.", ""]
    else:
        flagged_sorted = sorted(flagged, key=lambda x: x.analysis.severity, reverse=True)
        for item in flagged_sorted:
            issue = item.issue
            analysis = item.analysis
            lines += [
                "-" * 60,
                f"[SEV-{analysis.severity}] Issue #{issue.number}: {issue.title}",
                f"Repo   : {issue.repo}",
                f"Link   : {issue.html_url}",
                "",
                "Flagged for:",
                *[f"  • {r}" for r in analysis.reasons],
                "",
                "Suggested reply:",
                item.draft,
                "",
            ]

    lines += [
        "=" * 60,
        "These are AI-drafted suggestions. Review before posting.",
        "Burnout Guard — powered by AWS Bedrock",
        "=" * 60,
    ]

    return "\n".join(lines)
