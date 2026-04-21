import hashlib
import hmac
import os
from typing import Any

from github import fetch_pr_files, get_pr_head_sha, post_review_comments
from llm import review_code
from slack import send_slack_notification
from db import save_review, delete_review_by_pr


def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify the GitHub webhook HMAC-SHA256 signature.

    Computes the expected signature using GITHUB_WEBHOOK_SECRET and the
    raw request body, then compares it against the X-Hub-Signature-256
    header sent by GitHub. Returns True if valid, False otherwise.
    Prevents unauthorized parties from triggering reviews.

    Args:
        payload_body: Raw bytes of the incoming request body.
        signature_header: Value of the X-Hub-Signature-256 header.
    """
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        # No secret configured — skip verification (useful during local dev)
        return True

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


async def handle_closed_event(payload: dict[str, Any]) -> None:
    """
    Remove the review for a closed/merged PR from the database.

    Called when GitHub fires the 'closed' pull_request action (covers both
    merged and simply-closed PRs). If no review exists for the PR, does nothing.
    """
    repo = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    deleted = delete_review_by_pr(repo, pr_number)
    if deleted:
        print(f"[webhook] Deleted review for closed PR #{pr_number} in {repo}")
    else:
        print(f"[webhook] No review found for closed PR #{pr_number} in {repo} — nothing to delete")


async def handle_webhook_event(payload: dict[str, Any]) -> None:
    """
    Orchestrate the full PR review pipeline as a background task.

    Called after the webhook signature is verified and GitHub has already
    received a 200 OK response. Runs the following steps in order:
      1. Extract PR metadata (repo, number, title, URL, author) from payload.
      2. Fetch the list of changed files and their diffs from GitHub.
      3. Send the diff to the LLM for review.
      4. Post each LLM comment as an inline GitHub PR review comment.
      5. Send a summary notification to Slack.
      6. Persist the review result to SQLite.

    Handles errors gracefully at each step so a failure in one step
    (e.g. Slack being down) does not prevent the others from completing.

    Args:
        payload: Parsed JSON body from the GitHub webhook POST request.
    """
    pr = extract_pr_metadata(payload)
    print(f"[webhook] Processing PR #{pr['pr_number']} in {pr['repo']}: {pr['title']}")

    # Step 1: Fetch changed files
    try:
        files = await fetch_pr_files(pr["repo"], pr["pr_number"])
        print(f"[webhook] Fetched {len(files)} reviewable file(s)")
    except Exception as e:
        print(f"[webhook] Failed to fetch PR files: {e}")
        return

    if not files:
        print("[webhook] No reviewable files — skipping review")
        return

    # Step 2: LLM review
    try:
        review = await review_code(files, pr)
        print(
            f"[webhook] LLM review complete — "
            f"{len(review.get('comments', []))} comment(s) via {review.get('provider')}"
        )
    except Exception as e:
        print(f"[webhook] LLM review failed: {e}")
        return

    # Step 3: Fetch HEAD SHA and post inline comments to GitHub
    comment_count = 0
    try:
        commit_sha = await get_pr_head_sha(pr["repo"], pr["pr_number"])
        comment_count = await post_review_comments(
            pr["repo"],
            pr["pr_number"],
            commit_sha,
            review.get("comments", []),
        )
        print(f"[webhook] Posted {comment_count} inline comment(s) to GitHub")
    except Exception as e:
        print(f"[webhook] Failed to post GitHub comments: {e}")

    # Step 4: Slack notification (non-fatal) — only sent if comments were posted
    if comment_count > 0:
        try:
            sent = await send_slack_notification(pr, review, comment_count)
            if sent:
                print("[webhook] Slack notification sent")
        except Exception as e:
            print(f"[webhook] Slack notification failed: {e}")
    else:
        print("[webhook] No comments posted — skipping Slack notification")

    # Step 5: Persist to SQLite (non-fatal)
    try:
        review_id = save_review(pr, review, comment_count)
        print(f"[webhook] Review saved to database with ID {review_id}")
    except Exception as e:
        print(f"[webhook] Failed to save review to database: {e}")


def extract_pr_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Pull the relevant fields out of the raw GitHub webhook payload.

    Returns a dict with keys: repo (owner/name string), pr_number,
    title, url (html_url), and author (login). Used to avoid passing
    the large raw payload object through the rest of the pipeline.

    Args:
        payload: Full parsed GitHub webhook JSON payload.
    """
    pr_data = payload["pull_request"]
    return {
        "repo": payload["repository"]["full_name"],
        "pr_number": pr_data["number"],
        "title": pr_data["title"],
        "url": pr_data["html_url"],
        "author": pr_data["user"]["login"],
    }
