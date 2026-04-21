import os
from typing import Any

import httpx

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Severity badge colors for the Slack attachment side-bar
SEVERITY_COLORS = {
    "critical": "#FF0000",
    "warning": "#FFA500",
    "info": "#36A64F",
}

_SEVERITY_RANK = {"critical": 3, "warning": 2, "info": 1}


def get_highest_severity(comments: list[dict[str, Any]]) -> str:
    """
    Determine the most severe issue level across all review comments.

    Severity ranking: critical > warning > info. Returns 'info' if the
    comments list is empty. Used to pick the color of the Slack attachment.

    Args:
        comments: List of comment dicts, each with a 'severity' key.
    """
    highest = "info"
    for comment in comments:
        sev = comment.get("severity", "info")
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(highest, 0):
            highest = sev
    return highest


def build_slack_payload(
    pr: dict[str, Any],
    review: dict[str, Any],
    comment_count: int,
) -> dict[str, Any]:
    """
    Construct the Slack Block Kit message payload for a completed PR review.

    Builds a structured message containing:
      - PR title and repository name as the header
      - Author and LLM provider as context fields
      - The LLM summary text as a markdown section
      - Number of inline comments posted
      - A colored side-bar reflecting the highest severity found
      - A button that links directly to the PR on GitHub

    Args:
        pr: PR metadata dict with 'title', 'repo', 'author', and 'url' keys.
        review: Parsed LLM review dict with 'summary', 'comments', 'provider'.
        comment_count: Number of inline comments successfully posted to GitHub.
    """
    highest_severity = get_highest_severity(review.get("comments", []))
    color = SEVERITY_COLORS.get(highest_severity, SEVERITY_COLORS["info"])
    provider = review.get("provider", "groq")
    provider_label = "Claude (Sonnet)" if provider == "claude" else "Groq (Llama 3.3)"

    return {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"PR Review: {pr['title']}",
                            "emoji": True,
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Repo:* {pr['repo']}  |  "
                                    f"*Author:* @{pr['author']}  |  "
                                    f"*Provider:* {provider_label}"
                                ),
                            }
                        ],
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Summary:*\n{review['summary']}",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Inline Comments Posted:*\n{comment_count}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Highest Severity:*\n{highest_severity.upper()}",
                            },
                        ],
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View PR on GitHub",
                                    "emoji": True,
                                },
                                "url": pr["url"],
                                "style": "primary",
                            }
                        ],
                    },
                ],
            }
        ]
    }


async def send_slack_notification(
    pr: dict[str, Any],
    review: dict[str, Any],
    comment_count: int,
) -> bool:
    """
    POST a review summary notification to the configured Slack webhook URL.

    Builds the Block Kit payload via build_slack_payload() and sends it
    with an HTTP POST. Returns True on success (2xx response), False on
    any error (network failure, bad webhook URL, etc.) so callers can
    log the failure without crashing the pipeline.

    Args:
        pr: PR metadata dict with 'title', 'repo', 'author', and 'url' keys.
        review: Parsed LLM review dict with 'summary', 'comments', 'provider'.
        comment_count: Number of inline comments successfully posted to GitHub.
    """
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not configured — skipping Slack notification")
        return False

    payload = build_slack_payload(pr, review, comment_count)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(SLACK_WEBHOOK_URL, json=payload)
            return response.status_code == 200
    except Exception as e:
        print(f"Slack notification failed: {e}")
        return False
