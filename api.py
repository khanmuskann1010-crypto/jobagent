"""
REST API + dashboard server for the job search agent.

Serves the frontend (frontend/index.html) and exposes jobs.db, CV
tailoring, and the chat/voice command logic over HTTP, so the dashboard
can show listings, track application status, and let you talk to it
about your results.

Run:
    pip install -r requirements-api.txt -r requirements.txt
    uvicorn api:app --reload
Then open http://localhost:8000
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import chat_agent
import db
from groq import Groq
from cv_tailor import OUTPUT_DIR as CV_SUGGESTIONS_DIR
from cv_tailor import load_cv, save_tailored_cv, tailor_for_job

load_dotenv()
CV_SUGGESTIONS_DIR.mkdir(exist_ok=True)  # StaticFiles needs the dir to exist at mount time

app = FastAPI(title="Job Search Agent API")


class StatusUpdate(BaseModel):
    status: str


class ChatMessage(BaseModel):
    message: str
    history: list[dict] = []


def _sorted_jobs() -> list[dict]:
    """Canonical ordering: highest score first. The frontend's job list and
    chat's "job N" numbering both derive from this, so numbers line up."""
    return db.get_all_jobs()


@app.get("/api/jobs")
def list_jobs(min_score: int = 0, status: str | None = None):
    jobs = [j for j in _sorted_jobs() if j["score"] >= min_score]
    if status:
        jobs = [j for j in jobs if j["status"] == status]
    return jobs


@app.get("/api/jobs/{source}/{external_id}")
def get_job(source: str, external_id: str):
    job = db.get_job(source, external_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.patch("/api/jobs/{source}/{external_id}/status")
def set_status(source: str, external_id: str, body: StatusUpdate):
    if body.status not in db.STATUSES:
        raise HTTPException(400, f"status must be one of {db.STATUSES}")
    if not db.get_job(source, external_id):
        raise HTTPException(404, "job not found")
    db.update_status(source, external_id, body.status)
    return db.get_job(source, external_id)


@app.get("/api/applied")
def applied_jobs():
    """Jobs you've acted on: applied, interviewing, or rejected (not just scored)."""
    return [j for j in _sorted_jobs() if j["status"] in ("applied", "interviewing", "rejected")]


@app.get("/api/best-match")
def best_match():
    """Highest-scoring listing you haven't acted on yet - the "what's best for me" panel."""
    candidates = [j for j in _sorted_jobs() if j["status"] == "new"]
    return candidates[0] if candidates else None


@app.get("/api/progress")
def progress():
    return db.get_progress_stats()


@app.post("/api/jobs/{source}/{external_id}/tailor-cv")
def tailor_cv(source: str, external_id: str):
    job = db.get_job(source, external_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        cv_text = load_cv()
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    try:
        client = Groq()
    except Exception:
        raise HTTPException(400, "GROQ_API_KEY isn't configured - add it to .env to use CV tailoring.")
    suggestions = tailor_for_job(client, cv_text, job)
    if "error" in suggestions:
        raise HTTPException(502, suggestions["error"])
    path = save_tailored_cv(job, suggestions)
    return {**suggestions, "download_url": f"/cv-notes/{path.name}"}


@app.post("/api/chat")
def chat(body: ChatMessage):
    """Powers the dashboard's chat/voice panel with a real tool-using LLM
    agent (chat_agent.py) - free-form conversation, not fixed phrases. The
    frontend sends the prior turns as `history` so follow-ups ("tailor it
    for me") resolve correctly."""
    jobs = _sorted_jobs()

    try:
        cv_text = load_cv()
    except FileNotFoundError:
        cv_text = None

    try:
        client = Groq()
    except Exception:
        client = None

    history = body.history + [{"role": "user", "content": body.message}]
    reply, download_url = chat_agent.chat(client, history, jobs, cv_text)
    return {"reply": reply, "download_url": download_url}


app.mount("/cv-notes", StaticFiles(directory=str(CV_SUGGESTIONS_DIR)), name="cv-notes")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
