"""
analysis/analyze_issue.py
--------------------------
Sends each GitHub issue to AWS Bedrock (Amazon Nova Lite) for analysis.
Returns a structured AnalysisResult scoring sentiment, tone, and clarity.

Design notes:
- Nova Lite uses the Amazon Bedrock Converse API (converse / invoke_model
  with the amazon.nova-lite-v1:0 model ID and a messages-style payload).
- Prompt instructs the model to return ONLY valid JSON so we parse directly.
- JSON parse failures degrade gracefully: returns flagged=False with a
  warning log rather than crashing the whole Lambda run.
- Called in parallel via ThreadPoolExecutor in the orchestrator.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from github.fetch_issues import GitHubIssue
from config import AppConfig

logger = logging.getLogger(__name__)

# Truncate very long issue bodies to keep prompt tokens reasonable
MAX_BODY_CHARS = 3000

_SYSTEM_PROMPT = (
    "You are a code-of-conduct reviewer for open-source projects. "
    "You respond ONLY with valid JSON — no explanation, no markdown fences, no extra text."
)

_USER_PROMPT = """\
Analyze this GitHub issue and return ONLY valid JSON with exactly this shape:
{{
  "flagged": <boolean>,
  "severity": <1 | 2 | 3>,
  "sentiment": <"hostile" | "neutral" | "positive">,
  "tone": <"demanding" | "assertive" | "polite">,
  "clarity": <"clear" | "vague" | "no-repro-steps">,
  "reasons": [<string>, ...]
}}

Severity guide:
  1 = missing information only (no repro steps, no version, vague description)
  2 = dismissive or entitled tone toward maintainers
  3 = aggressive, threatening, or code-of-conduct violating language

Only set flagged=true if the issue genuinely needs maintainer intervention.
Well-written but incomplete issues should be flagged at severity 1.
Clear, polite, and complete issues should NOT be flagged.

Issue Title: {title}
Issue Body:
---
{body}
---"""


@dataclass
class AnalysisResult:
    flagged: bool
    severity: Literal[1, 2, 3] = 1
    sentiment: Literal["hostile", "neutral", "positive"] = "neutral"
    tone: Literal["demanding", "assertive", "polite"] = "polite"
    clarity: Literal["clear", "vague", "no-repro-steps"] = "clear"
    reasons: List[str] = field(default_factory=list)


def analyze_issue(issue: GitHubIssue, config: AppConfig) -> AnalysisResult:
    """
    Invoke Bedrock (Nova Lite) to analyze a single GitHub issue.
    Returns AnalysisResult. Never raises — degrades to flagged=False on error.
    """
    body_truncated = issue.body[:MAX_BODY_CHARS]

    user_text = _USER_PROMPT.format(
        title=issue.title,
        body=body_truncated,
    )

    # Nova Lite uses the Converse API — messages array + optional system prompt
    bedrock = boto3.client("bedrock-runtime", region_name=config.TARGET_REGION)

    try:
        response = bedrock.converse(
            modelId=config.bedrock_model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[
                {"role": "user", "content": [{"text": user_text}]}
            ],
            inferenceConfig={
                "maxTokens": 512,
                "temperature": 0.0,   # deterministic for structured JSON
            },
        )
        # Nova Lite response shape: output.message.content[0].text
        text = response["output"]["message"]["content"][0]["text"].strip()
        data = json.loads(text)

    except (BotoCoreError, ClientError) as exc:
        logger.warning(
            "[analysis] Bedrock call failed for issue #%d in %s: %s",
            issue.number, issue.repo, exc,
        )
        return AnalysisResult(flagged=False)
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "[analysis] Failed to parse Bedrock response for issue #%d in %s: %s",
            issue.number, issue.repo, exc,
        )
        return AnalysisResult(flagged=False)

    # Validate and coerce severity
    severity = data.get("severity", 1)
    if severity not in (1, 2, 3):
        severity = 1

    result = AnalysisResult(
        flagged=bool(data.get("flagged", False)),
        severity=severity,
        sentiment=data.get("sentiment", "neutral"),
        tone=data.get("tone", "polite"),
        clarity=data.get("clarity", "clear"),
        reasons=data.get("reasons", []),
    )

    logger.info(
        "[analysis] Issue #%d (%s): flagged=%s severity=%d sentiment=%s",
        issue.number, issue.repo, result.flagged, result.severity, result.sentiment,
    )
    return result
