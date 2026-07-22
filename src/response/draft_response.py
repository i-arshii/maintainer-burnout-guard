"""
response/draft_response.py
---------------------------
Drafts an empathetic, firm reply template for a flagged GitHub issue using
Amazon Nova Lite on Bedrock. Called only for flagged issues.

Prompt strategy varies by severity:
  1 → Warmly ask for the specific missing information
  2 → Gently reframe the conversation toward collaboration
  3 → Acknowledge, reference CoC non-accusatorially, invite re-engagement

The model is never told it is AI. The reply must read as if written
by the maintainer themselves.
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import AppConfig
from src.github.fetch_issues import GitHubIssue
from src.analysis.analyze_issue import AnalysisResult

logger = logging.getLogger(__name__)

MAX_BODY_CHARS = 2000

_SYSTEM_PROMPT = (
    "You are a kind, experienced open-source maintainer writing a reply "
    "to a GitHub issue. You write in plain, warm, human prose. "
    "You never mention AI, automation, or bots. "
    "You never exceed 150 words."
)

_PROMPT_BY_SEVERITY = {
    1: """\
This issue is missing key information needed to reproduce or investigate it.

Write a reply that:
- Opens with a warm, genuine acknowledgment of the reporter's effort
- Asks specifically for what is missing: reproduction steps, environment \
details (OS, version), expected vs actual behaviour — only ask for what \
is genuinely absent from the issue body
- Closes encouragingly, inviting them to update the issue

Issue Title: {title}
Issue Body:
---
{body}
---
Flagged reasons: {reasons}

Reply (under 150 words, plain text only):""",

    2: """\
This issue uses a dismissive or entitled tone toward maintainers.

Write a reply that:
- Opens with empathy — acknowledge their frustration if evident
- Does NOT lecture or point out the tone problem directly
- Reframes the conversation as a collaboration: "let's figure this out together"
- Asks any clarifying questions needed to move forward
- Closes warmly

Issue Title: {title}
Issue Body:
---
{body}
---
Flagged reasons: {reasons}

Reply (under 150 words, plain text only):""",

    3: """\
This issue contains aggressive, threatening, or code-of-conduct violating language.

Write a reply that:
- Opens by briefly thanking them for taking the time to raise the issue
- Calmly and non-accusatorially references the project's Code of Conduct \
(do not quote it, just mention it exists)
- Invites them to re-engage constructively if they wish
- Is firm but never hostile or defensive

Issue Title: {title}
Issue Body:
---
{body}
---
Flagged reasons: {reasons}

Reply (under 150 words, plain text only):""",
}


def draft_response(
    issue: GitHubIssue,
    analysis: AnalysisResult,
    config: AppConfig,
) -> str:
    """
    Invoke Nova Lite to draft a reply for a flagged issue.
    Returns plain text. Raises on Bedrock failure (caller handles).
    """
    severity = analysis.severity if analysis.severity in (1, 2, 3) else 1
    reasons_text = "; ".join(analysis.reasons) if analysis.reasons else "see severity level"

    user_text = _PROMPT_BY_SEVERITY[severity].format(
        title=issue.title,
        body=issue.body[:MAX_BODY_CHARS],
        reasons=reasons_text,
    )

    bedrock = boto3.client("bedrock-runtime", region_name=config.TARGET_REGION)

    try:
        response = bedrock.converse(
            modelId=config.bedrock_model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[
                {"role": "user", "content": [{"text": user_text}]}
            ],
            inferenceConfig={
                "maxTokens": 300,
                "temperature": 0.4,   # slight creativity for natural prose
            },
        )
        draft = response["output"]["message"]["content"][0]["text"].strip()
    except (BotoCoreError, ClientError) as exc:
        logger.error(
            "[draft] Bedrock call failed for issue #%d in %s: %s",
            issue.number, issue.repo, exc,
        )
        raise

    logger.info(
        "[draft] Drafted reply for issue #%d (%s) severity=%d (%d words)",
        issue.number, issue.repo, severity, len(draft.split()),
    )
    return draft
