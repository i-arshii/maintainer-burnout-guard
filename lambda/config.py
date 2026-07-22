"""
config.py
---------
Loads all runtime configuration from AWS SSM Parameter Store in a single
batch call at Lambda cold start. Raises clearly if any required parameter
is missing so failures are obvious in CloudWatch rather than silent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# All parameter paths expected in SSM
_PARAM_PATHS = {
    "github_token":    "/burnout-guard/github-token",
    "repos":           "/burnout-guard/repos",
    "ses_from":        "/burnout-guard/ses-from",
    "ses_to":          "/burnout-guard/ses-to",
    "lookback_hours":  "/burnout-guard/lookback-hours",
    "bedrock_model_id": "/burnout-guard/bedrock-model-id",
}


@dataclass
class AppConfig:
    github_token: str
    repos: List[str]           # parsed from comma-separated SSM value
    ses_from: str
    ses_to: str
    lookback_hours: int        # default 24
    bedrock_model_id: str
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "us-east-1"))


def load_config() -> AppConfig:
    """
    Fetch all SSM parameters in a single GetParameters call.
    WithDecryption=True handles the SecureString github-token.
    Raises RuntimeError with a clear message on any missing param.
    """
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    names = list(_PARAM_PATHS.values())

    try:
        response = ssm.get_parameters(Names=names, WithDecryption=True)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"[config] Failed to fetch SSM parameters: {exc}") from exc

    # Index by name for easy lookup
    fetched = {p["Name"]: p["Value"] for p in response.get("Parameters", [])}

    # Detect any missing params and fail loudly
    missing = [path for path in names if path not in fetched]
    if missing:
        raise RuntimeError(
            f"[config] Missing required SSM parameters: {missing}\n"
            "Provision them with: aws ssm put-parameter --name <path> --value <val>"
        )

    raw_repos = fetched[_PARAM_PATHS["repos"]]
    repos = [r.strip() for r in raw_repos.split(",") if r.strip()]
    if not repos:
        raise RuntimeError("[config] /burnout-guard/repos is empty — add at least one owner/repo")

    try:
        lookback_hours = int(fetched[_PARAM_PATHS["lookback_hours"]])
    except ValueError:
        lookback_hours = 24  # safe default

    return AppConfig(
        github_token=fetched[_PARAM_PATHS["github_token"]],
        repos=repos,
        ses_from=fetched[_PARAM_PATHS["ses_from"]],
        ses_to=fetched[_PARAM_PATHS["ses_to"]],
        lookback_hours=lookback_hours,
        bedrock_model_id=fetched[_PARAM_PATHS["bedrock_model_id"]],
    )
