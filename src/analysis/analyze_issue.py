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
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from github.fetch_issues import GitHubIssue
from config import AppConfig

logger = logging.getLogger(__name__)

# Truncate very long issue bodies to keep prompt tokens reasonable
MAX_BODY_CHARS = 3000

_SYSTEM_PROMPT = (
    "You are a code-of-conduct reviewer for open-source projects. "
    "Your output must be single-line raw JSON. Do not include markdown blocks, "
    "do not include backticks (```), and do not wrap text in a 'json' indicator code fence. "
    "Do not provide explanations before or after the JSON structure."
)

_USER_PROMPT = """\
Analyze the provided GitHub issue and evaluate its text contents against our criteria.
You must return your output strictly in this JSON format:
{{
  "flagged": true,
  "severity": 1,
  "sentiment": "neutral",
  "tone": "polite",
  "clarity": "clear",
  "reasons": ["Personalized reason citing the issue components directly"],
  "suggested_reply": "Deeply personal, context-specific response for this unique issue."
}}

Where values match these definitions:
- flagged: boolean (true or false)
- severity: integer (1, 2, or 3)
- sentiment: string ("hostile", "neutral", or "positive")
- tone: string ("demanding", "assertive", or "polite")
- clarity: string ("clear", "vague", or "no-repro-steps")

CRITICAL INSTRUCTIONS FOR "reasons":
Never use template phrases like "missing system version tracks" or "missing repro steps". Describe exactly what is missing based strictly on the domain of the title. For example, if the issue is about a data feed parse artifact (like pricing percentages), state that specific sample pricing logs or data payloads are missing.

CRITICAL INSTRUCTIONS FOR "suggested_reply":
- Do NOT generate a list, bullet points, or numbered steps.
- Do NOT ask generic boilerplate questions like "What OS are you using?" or "What are the steps to reproduce?".
- Write a warm, professional, human paragraph (2-3 sentences max) mentioning specific items from the title.
- For example, if the issue mentions 'movers feed parse artifacts (+874% sugar)', write a reply like: "Thanks for tracking down these extreme parse shifts in the consumer-prices feed! To help us isolate the math error in the basket metrics, could you paste a raw snippet of the upstream feed payload or the retailer basket object you were parsing?"

Issue Title: {title}
Issue Body:
---
{body}
---

CRITICAL: Return the raw JSON block immediately. Do not use code blocks or markdown formatting."""


@dataclass
class AnalysisResult:
    flagged: bool
    severity: Literal[1, 2, 3] = 1
    sentiment: Literal["hostile", "neutral", "positive"] = "neutral"
    tone: Literal["demanding", "assertive", "polite"] = "polite"
    clarity: Literal["clear", "vague", "no-repro-steps"] = "clear"
    reasons: List[str] = field(default_factory=list)
    suggested_reply: str = ""  # New field to hold the custom response string



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

    # Advanced retry fallback config mapping definition block
    retry_config = Config(
        retries={
            "max_attempts": 10,
            "mode": "standard"
        }
    )

    bedrock = boto3.client(
        "bedrock-runtime", 
        region_name=config.TARGET_REGION,
        config=retry_config
    )

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
    
    # Extract reasons from data first
    reasons = data.get("reasons", [])

    # If flagged but the model provided no reasons, apply fallback reasons
    if bool(data.get("flagged", False)) and not reasons:
        if severity == 1:
            reasons = ["Issue tracks minimal description context or missing technical reproduction parameters."]
        else:
            reasons = ["Maintainer review flagged due to text conversational pacing attributes."]

    suggested_reply = data.get("suggested_reply", "").strip()
    if not suggested_reply:
        if severity == 1:
            suggested_reply = "Thanks for flagging this! Could you share a quick diagnostic log snippet or example data payload matching this behavior so we can investigate the root cause?"
        else:
            suggested_reply = "Thank you for the report. Our team will review this behavior against our project workflow updates shortly."

    result = AnalysisResult(
        flagged=bool(data.get("flagged", False)),
        severity=severity,
        sentiment=data.get("sentiment", "neutral"),
        tone=data.get("tone", "polite"),
        clarity=data.get("clarity", "clear"),
        reasons=reasons,
        suggested_reply=suggested_reply,
    )

    logger.info(
        "[analysis] Issue #%d (%s): flagged=%s severity=%d sentiment=%s",
        issue.number, issue.repo, result.flagged, result.severity, result.sentiment,
    )
    return result
