import json
import os
from typing import Any

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")

MAX_COMMENTS = 5

REVIEW_PROMPT_TEMPLATE = """
You are a senior software engineer performing a code review.

Review the following pull request diff and return a JSON object with:
- "summary": a 1-2 sentence plain-English summary of the overall review
- "comments": an array of issues found — only include a comment if it is strictly necessary

Rules for comments:
- Only flag real problems: bugs, security issues, crashes, missing error handling, logic errors
- If the code is correct and safe, return an empty comments array — do NOT invent issues
- Never comment on style, formatting, naming, or minor improvements
- A comment must describe a concrete problem that would cause incorrect behavior or a failure

Each comment in the array must have:
- "path": the file path (string)
- "line": the line number in the file to attach the comment to (integer)
- "body": the review comment text explaining the issue and suggesting a fix
- "severity": one of "critical", "warning", or "info"

Return only valid JSON, no prose.

Pull Request: {pr_title}
Repository: {repo}
Author: {author}

Files changed:
{diff_content}
"""


def build_prompt(files: list[dict[str, Any]], pr: dict[str, Any]) -> str:
    """
    Construct the review prompt string from changed files and PR metadata.

    Formats each file's patch into the REVIEW_PROMPT_TEMPLATE. Truncates
    individual patches that are too long to keep the total prompt within
    the model's context window.

    Args:
        files: List of file dicts with 'filename' and 'patch' keys.
        pr: PR metadata dict with 'title', 'repo', and 'author' keys.
    """
    diff_parts = []
    for file in files:
        filename = file.get("filename", "")
        patch = file.get("patch", "")
        lines = patch.splitlines()
        if len(lines) > 200:
            patch = "\n".join(lines[:200]) + "\n... (truncated)"
        diff_parts.append(f"### {filename}\n```diff\n{patch}\n```")

    return REVIEW_PROMPT_TEMPLATE.format(
        pr_title=pr.get("title", ""),
        repo=pr.get("repo", ""),
        author=pr.get("author", ""),
        diff_content="\n\n".join(diff_parts),
    )


async def review_code(
    files: list[dict[str, Any]], pr: dict[str, Any]
) -> dict[str, Any]:
    """
    Send the PR diff to the active LLM provider and return a structured review.

    This is the single function that changes between Day 1 (Groq) and Day 2
    (Claude). The prompt and output shape are identical regardless of provider.

    Calls build_prompt() to construct the prompt, sends it to the configured
    provider, then parses and validates the JSON response. Falls back to an
    empty-comments response if the LLM returns malformed JSON.

    Returns a dict with:
        - "summary" (str): plain-English overview of the review
        - "comments" (list): up to MAX_COMMENTS inline comment objects
        - "provider" (str): which LLM was used ("groq" or "claude")

    Args:
        files: Filtered list of changed file dicts from github.fetch_pr_files().
        pr: PR metadata dict with 'title', 'repo', 'author', and 'url' keys.
    """
    prompt = build_prompt(files, pr)
    try:
        if LLM_PROVIDER == "claude":
            raw = await _call_claude(prompt)
        else:
            raw = await _call_groq(prompt)
        result = parse_llm_response(raw)
    except Exception as e:
        print(f"LLM call failed: {e}")
        result = {
            "summary": "Review could not be completed due to an LLM error.",
            "comments": [],
        }

    result["provider"] = LLM_PROVIDER
    return result


async def _call_groq(prompt: str) -> str:
    """
    Send a prompt to the Groq API and return the raw text response.

    Uses the llama-3.3-70b-versatile model. Sets temperature to 0 for
    deterministic, consistent review output.

    Args:
        prompt: The fully rendered review prompt string.
    """
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content


async def _call_claude(prompt: str) -> str:
    """
    Send a prompt to the Anthropic Claude API and return the raw text response.

    Uses claude-sonnet-4-5 model. Sets max_tokens to 1024 and temperature
    to 0 for deterministic output.

    Args:
        prompt: The fully rendered review prompt string.
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def parse_llm_response(raw: str) -> dict[str, Any]:
    """
    Parse and validate the raw JSON string returned by the LLM.

    Strips any markdown code fences (```json ... ```) the model may have
    added. Validates that 'summary' is a string and 'comments' is a list.
    Returns a safe default dict if parsing fails so the pipeline never
    crashes due to a bad LLM response.

    Args:
        raw: The raw text output from the LLM.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop opening fence line (e.g. ```json)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {
            "summary": "Could not parse the LLM response as JSON.",
            "comments": [],
        }

    if not isinstance(data.get("summary"), str):
        data["summary"] = "No summary provided."
    if not isinstance(data.get("comments"), list):
        data["comments"] = []

    return data
