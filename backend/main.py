import json
import os
from dotenv import load_dotenv

load_dotenv()  # must run before any module that reads env vars at import time

from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from webhook import handle_webhook_event, handle_closed_event, verify_signature
from db import init_db, get_all_reviews, get_review_by_id

app = FastAPI(title="PR Review Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize the SQLite database on app startup."""
    init_db()


@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive GitHub webhook POST requests for PR events.

    Verifies the request signature using GITHUB_WEBHOOK_SECRET, responds
    immediately with 200 OK, and dispatches the review pipeline as a
    background task so GitHub does not time out waiting for a response.

    Listens for 'opened' and 'synchronize' pull_request actions only.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"event '{event_type}' not handled"}

    payload = json.loads(body)
    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "closed"):
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    if action == "closed":
        background_tasks.add_task(handle_closed_event, payload)
    else:
        background_tasks.add_task(handle_webhook_event, payload)
    return {"status": "accepted", "action": action}


@app.get("/reviews")
async def list_reviews():
    """
    Return all stored PR reviews from the SQLite database.

    Used by the frontend dashboard (index page) to render the list of
    reviewed PRs. Returns a JSON array of review objects ordered by
    most recent first.
    """
    return get_all_reviews()


@app.get("/reviews/{review_id}")
async def get_review(review_id: int):
    """
    Return a single PR review by its database ID.

    Used by the frontend detail page (/pr/[id]) to display the full
    review including all individual inline comments that were posted.
    Returns 404 if the review does not exist.
    """
    review = get_review_by_id(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.

    Returns a JSON object with status 'ok'. Used by Railway and other
    deployment platforms to confirm the service is running.
    """
    return {"status": "ok"}
