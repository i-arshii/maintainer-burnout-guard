"""
email/send_digest.py
---------------------
Delivers the nightly digest via Amazon SES.
Sends both HTML and plain-text body parts.
Logs and re-raises on SES failure so the Lambda invocation is marked failed.
"""

from __future__ import annotations

import logging
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from lambda.config import AppConfig

logger = logging.getLogger(__name__)


def send_digest(
    html_body: str,
    text_body: str,
    flagged_count: int,
    run_date: datetime,
    config: AppConfig,
) -> None:
    """
    Send the digest email via SES.

    Subject format: 🛡️ Burnout Guard – {N} issues flagged – {YYYY-MM-DD}

    Raises ClientError on SES failure after logging the error.
    The SES from-address must be a verified SES identity.
    """
    date_str = run_date.strftime("%Y-%m-%d")
    subject = f"\U0001f6e1\ufe0f Burnout Guard \u2013 {flagged_count} issue{'s' if flagged_count != 1 else ''} flagged \u2013 {date_str}"

    ses = boto3.client("ses", region_name=config.TARGET_REGION)

    try:
        response = ses.send_email(
            Source=config.ses_from,
            Destination={
                "ToAddresses": [config.ses_to],
            },
            Message={
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": text_body,
                        "Charset": "UTF-8",
                    },
                    "Html": {
                        "Data": html_body,
                        "Charset": "UTF-8",
                    },
                },
            },
        )
        message_id = response.get("MessageId", "unknown")
        logger.info(
            "[email] Digest sent successfully — MessageId=%s subject=%r",
            message_id, subject,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error(
            "[email] Failed to send digest via SES from=%s to=%s: %s",
            config.ses_from, config.ses_to, exc,
        )
        raise
