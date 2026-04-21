import sqlite3
import os
from typing import Any

DB_PATH = os.getenv("DB_PATH", "reviews.db")

_SEVERITY_RANK = {"critical": 3, "warning": 2, "info": 1}


def get_connection() -> sqlite3.Connection:
    """
    Open and return a SQLite connection to the reviews database.

    Sets row_factory to sqlite3.Row so rows can be accessed by column name
    as well as index. The database file is created at DB_PATH if it does
    not already exist.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create the reviews and comments tables if they do not yet exist.

    Called once at application startup from main.py. Safe to run on every
    startup — uses CREATE TABLE IF NOT EXISTS. Schema:

    reviews:
        id          INTEGER PRIMARY KEY AUTOINCREMENT
        repo        TEXT NOT NULL          -- 'owner/name'
        pr_number   INTEGER NOT NULL
        title       TEXT NOT NULL
        url         TEXT NOT NULL          -- GitHub html_url
        author      TEXT NOT NULL          -- GitHub login
        summary     TEXT NOT NULL          -- LLM summary string
        severity    TEXT NOT NULL          -- highest severity across all comments
        comment_count INTEGER NOT NULL
        provider    TEXT NOT NULL          -- 'groq' or 'claude'
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP

    comments:
        id          INTEGER PRIMARY KEY AUTOINCREMENT
        review_id   INTEGER NOT NULL REFERENCES reviews(id)
        path        TEXT NOT NULL          -- file path
        line        INTEGER NOT NULL
        body        TEXT NOT NULL
        severity    TEXT NOT NULL
    """
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reviews (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                repo          TEXT NOT NULL,
                pr_number     INTEGER NOT NULL,
                title         TEXT NOT NULL,
                url           TEXT NOT NULL,
                author        TEXT NOT NULL,
                summary       TEXT NOT NULL,
                severity      TEXT NOT NULL,
                comment_count INTEGER NOT NULL,
                provider      TEXT NOT NULL,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS comments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL REFERENCES reviews(id),
                path      TEXT NOT NULL,
                line      INTEGER NOT NULL,
                body      TEXT NOT NULL,
                severity  TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _highest_severity(comments: list[dict[str, Any]]) -> str:
    highest = "info"
    for c in comments:
        sev = c.get("severity", "info")
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(highest, 0):
            highest = sev
    return highest


def save_review(
    pr: dict[str, Any],
    review: dict[str, Any],
    comment_count: int,
) -> int:
    """
    Insert a completed review and its inline comments into the database.

    Writes one row to the reviews table and one row per comment to the
    comments table inside a single transaction. Returns the new review's
    integer ID so callers can reference it if needed.

    Args:
        pr: PR metadata dict with 'repo', 'pr_number', 'title', 'url', 'author'.
        review: Parsed LLM review dict with 'summary', 'comments', 'provider'.
        comment_count: Number of inline comments successfully posted to GitHub.
    """
    severity = _highest_severity(review.get("comments", []))
    conn = get_connection()
    try:
        # Always replace — LLM's latest review is the source of truth
        existing = conn.execute(
            "SELECT id FROM reviews WHERE repo = ? AND pr_number = ?",
            (pr["repo"], pr["pr_number"]),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM comments WHERE review_id = ?", (existing["id"],))
            conn.execute("DELETE FROM reviews WHERE id = ?", (existing["id"],))

        # Only insert if LLM found issues — 0 comments means PR is clean, hide the card
        if comment_count == 0:
            conn.commit()
            return -1

        cursor = conn.execute(
            """
            INSERT INTO reviews (repo, pr_number, title, url, author, summary, severity, comment_count, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pr["repo"],
                pr["pr_number"],
                pr["title"],
                pr["url"],
                pr["author"],
                review["summary"],
                severity,
                comment_count,
                review["provider"],
            ),
        )
        review_id = cursor.lastrowid
        for comment in review.get("comments", []):
            conn.execute(
                """
                INSERT INTO comments (review_id, path, line, body, severity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    comment["path"],
                    comment["line"],
                    comment["body"],
                    comment["severity"],
                ),
            )
        conn.commit()
        return review_id
    finally:
        conn.close()


def delete_review_by_pr(repo: str, pr_number: int) -> bool:
    """
    Delete a review and its comments when a PR is closed/merged.

    Returns True if a review was found and deleted, False if no matching
    review existed (e.g. the PR was never reviewed).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM reviews WHERE repo = ? AND pr_number = ?",
            (repo, pr_number),
        ).fetchone()
        if row is None:
            return False
        review_id = row["id"]
        conn.execute("DELETE FROM comments WHERE review_id = ?", (review_id,))
        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_reviews() -> list[dict[str, Any]]:
    """
    Fetch all reviews from the database ordered by most recent first.

    Returns a list of dicts (one per review row) suitable for JSON
    serialization. Does not include the nested comments — use
    get_review_by_id() for the full detail view.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.*,
                (SELECT COUNT(*) FROM comments c WHERE c.review_id = r.id AND c.severity = 'critical') AS critical_count,
                (SELECT COUNT(*) FROM comments c WHERE c.review_id = r.id AND c.severity = 'warning')  AS warning_count,
                (SELECT COUNT(*) FROM comments c WHERE c.review_id = r.id AND c.severity = 'info')     AS info_count
            FROM reviews r
            WHERE r.comment_count > 0
            ORDER BY r.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_review_by_id(review_id: int) -> dict[str, Any] | None:
    """
    Fetch a single review and all its associated comments by ID.

    Returns a dict with all review fields plus a nested 'comments' list.
    Returns None if no review with the given ID exists.

    Args:
        review_id: The integer primary key of the review to fetch.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        comments = conn.execute(
            "SELECT * FROM comments WHERE review_id = ?", (review_id,)
        ).fetchall()
        result["comments"] = [dict(c) for c in comments]
        return result
    finally:
        conn.close()
