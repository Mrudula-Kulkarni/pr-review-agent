import os
from typing import Any

import httpx

GITHUB_API_BASE = "https://api.github.com"

# Files to skip during review — lock files, generated files, etc.
EXCLUDED_EXTENSIONS = {".lock", ".sum", ".generated", ".pb.go"}
EXCLUDED_FILENAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "go.sum"}
MAX_FILES = 10
MAX_PATCH_LINES = 500


def get_auth_headers() -> dict[str, str]:
    """
    Return the HTTP headers required for authenticated GitHub API requests.

    Includes Authorization (Bearer token) and Accept header for the
    GitHub REST API v3 JSON format.
    """
    return {
        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.v3+json",
    }


async def fetch_pr_files(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """
    Fetch the list of changed files and their diffs for a pull request.

    Calls GET /repos/{repo}/pulls/{pr_number}/files on the GitHub API.
    Filters out lock files, generated files, and patches exceeding
    MAX_PATCH_LINES lines. Returns at most MAX_FILES files to stay within
    LLM token limits.

    Each returned dict contains at minimum: 'filename', 'patch' (the diff),
    and 'status' (added/modified/removed).

    Args:
        repo: The full repository name in 'owner/name' format.
        pr_number: The pull request number to fetch files for.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/files"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_auth_headers())
        response.raise_for_status()
        files = response.json()

    filtered = []
    for file in files:
        filename = file.get("filename", "")
        patch = file.get("patch")
        if should_skip_file(filename, patch):
            continue
        filtered.append(file)
        if len(filtered) >= MAX_FILES:
            break

    return filtered


def should_skip_file(filename: str, patch: str | None) -> bool:
    """
    Determine whether a file should be excluded from the LLM review.

    Returns True (skip) if the file has an excluded extension, is in the
    excluded filenames list, has no patch (binary file or rename-only),
    or if the patch exceeds MAX_PATCH_LINES lines.

    Args:
        filename: The relative path of the file within the repository.
        patch: The raw unified diff string for the file, or None.
    """
    if patch is None:
        return True

    _, ext = os.path.splitext(filename)
    if ext in EXCLUDED_EXTENSIONS:
        return True

    base = os.path.basename(filename)
    if base in EXCLUDED_FILENAMES:
        return True

    if len(patch.splitlines()) > MAX_PATCH_LINES:
        return True

    return False


async def post_review_comments(
    repo: str,
    pr_number: int,
    commit_sha: str,
    comments: list[dict[str, Any]],
) -> int:
    """
    Post inline review comments on a GitHub pull request.

    Uses REQUEST_CHANGES event when comments exist (blocks merge) and
    APPROVE event when no comments (unblocks merge). Falls back to
    posting one comment at a time if the batch is rejected with 422.

    Returns the number of comments successfully posted.

    Args:
        repo: Full repository name in 'owner/name' format.
        pr_number: The pull request number to comment on.
        commit_sha: The HEAD commit SHA of the PR branch (required by GitHub API).
        comments: List of dicts with keys 'path', 'line', 'body', 'severity'.
    """
    if os.getenv("SIMULATE_COMMENT_FAILURE", "").lower() == "true":
        raise RuntimeError("Simulated GitHub comment failure (SIMULATE_COMMENT_FAILURE=true)")

    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"

    # No issues found — approve to unblock merge
    # Note: GitHub returns 422 if the reviewer is the PR author (can't self-approve) — skip gracefully
    if not comments:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=get_auth_headers(), json={
                "commit_id": commit_sha,
                "body": "No issues found. PR looks good to merge.",
                "event": "APPROVE",
            })
            if response.status_code == 422:
                print("[github] Skipping APPROVE — cannot approve your own PR")
            else:
                response.raise_for_status()
        return 0

    github_comments = [
        {
            "path": c["path"],
            "line": c["line"],
            "body": c["body"],
            "side": "RIGHT",
        }
        for c in comments
    ]

    payload = {
        "commit_id": commit_sha,
        "body": "Issues found. Please address the inline comments before merging.",
        "event": "REQUEST_CHANGES",
        "comments": github_comments,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=get_auth_headers(), json=payload)

        if response.status_code in (200, 201):
            return len(comments)

        if response.status_code == 422:
            # REQUEST_CHANGES rejected (e.g. self-review) — fall back to COMMENT event
            posted = 0
            for comment in github_comments:
                single_payload = {
                    "commit_id": commit_sha,
                    "body": "Issues found. Please address the inline comments before merging.",
                    "event": "COMMENT",
                    "comments": [comment],
                }
                r = await client.post(
                    url, headers=get_auth_headers(), json=single_payload
                )
                if r.status_code in (200, 201):
                    posted += 1
            return posted

        response.raise_for_status()

    return 0


async def get_pr_head_sha(repo: str, pr_number: int) -> str:
    """
    Fetch the HEAD commit SHA for a pull request branch.

    Calls GET /repos/{repo}/pulls/{pr_number} and returns the
    head.sha field. Required when posting inline review comments
    via the GitHub API.

    Args:
        repo: Full repository name in 'owner/name' format.
        pr_number: The pull request number.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_auth_headers())
        response.raise_for_status()
        data = response.json()
    return data["head"]["sha"]
