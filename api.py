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

import csv
import io
import threading
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import chat_agent
import db
import dedupe
import groq_usage
import interview_agent
import link_checker
import main as fetch_main
import rejection_insights
from groq import Groq
from cover_letter import generate_cover_letter, save_cover_letter
from cv_tailor import OUTPUT_DIR as CV_SUGGESTIONS_DIR
from cv_tailor import load_cv, save_tailored_cv, tailor_for_job

load_dotenv()
CV_SUGGESTIONS_DIR.mkdir(exist_ok=True)  # StaticFiles needs the dir to exist at mount time
db.auto_archive_stale_jobs()  # quietly tidy up on every server start, same housekeeping main.py does

AUTO_FETCH_META_KEY = "last_auto_fetch_date"
_fetch_state = {"status": "idle", "new": 0, "dead": 0, "error": None}  # idle | running | done | error


def _run_auto_fetch():
    """Runs once per calendar day, the first time the server starts that
    day - not on every --reload restart, which would otherwise burn through
    Adzuna/France Travail calls and the Groq daily token budget on every
    file save during development. Also sweeps a batch of already-seen
    listings to flag ones that have been pulled from their platform (see
    link_checker.py), so the queue doesn't keep pointing you at dead links."""
    global _fetch_state
    today = date.today().isoformat()
    if db.get_meta(AUTO_FETCH_META_KEY) == today:
        return
    _fetch_state = {"status": "running", "new": 0, "dead": 0, "error": None}
    try:
        result = fetch_main.run_fetch()
        dead = link_checker.check_listings(db.get_jobs_to_recheck())
        db.set_meta(AUTO_FETCH_META_KEY, today)
        _fetch_state = {"status": "done", "new": result["new"], "dead": dead, "error": None}
    except Exception as e:
        _fetch_state = {"status": "error", "new": 0, "dead": 0, "error": str(e)}

try:
    import gmail_agent
    GMAIL_IMPORT_ERROR = None
except ImportError as e:
    gmail_agent = None
    GMAIL_IMPORT_ERROR = str(e)  # Gmail is optional - don't crash the whole server over it

app = FastAPI(title="Job Search Agent API")


@app.on_event("startup")
def _startup_auto_fetch():
    threading.Thread(target=_run_auto_fetch, daemon=True).start()


class StatusUpdate(BaseModel):
    status: str


class InterviewUpdate(BaseModel):
    when: str | None = None


class ChatMessage(BaseModel):
    message: str
    history: list[dict] = []


class InterviewMessage(BaseModel):
    history: list[dict] = []


def _groq_client() -> Groq | None:
    try:
        return Groq()
    except Exception:
        return None


def _sorted_jobs() -> list[dict]:
    """Canonical ordering: highest score first, with same-posting duplicates
    across sources merged into one card (dedupe.py). The frontend's job
    list and chat's "job N" numbering both derive from this, so numbers
    line up everywhere - and both see the same merged view."""
    return dedupe.group_duplicates(db.get_all_jobs())


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


@app.get("/api/fetch-status")
def fetch_status():
    """Lets the dashboard show a "fetching today's listings…" indicator for
    the automatic on-startup fetch (see _run_auto_fetch above)."""
    return _fetch_state


@app.get("/api/groq-usage")
def groq_usage_endpoint():
    """Tokens used today, tracked by this app from Groq's own response data
    (Groq doesn't expose a daily-quota API) - see groq_usage.py."""
    return groq_usage.get_usage()


@app.get("/api/progress/trend")
def progress_trend(days: int = 30):
    return db.get_status_trend(days=days)


@app.get("/api/follow-ups")
def follow_ups(days: int = 7):
    """Applications with no status update in `days` - worth a nudge."""
    return db.get_stale_applications(days=days)


@app.get("/api/calendar")
def calendar():
    """Jobs with a scheduled interview, soonest first."""
    return db.get_upcoming_interviews()


@app.patch("/api/jobs/{source}/{external_id}/interview")
def set_interview(source: str, external_id: str, body: InterviewUpdate):
    if not db.get_job(source, external_id):
        raise HTTPException(404, "job not found")
    db.set_interview_datetime(source, external_id, body.when)
    return db.get_job(source, external_id)


@app.get("/api/export/applied.csv")
def export_applied_csv():
    rows = [j for j in _sorted_jobs() if j["status"] in ("applied", "interviewing", "rejected")]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["title", "company", "location", "score", "status", "status_updated_at", "salary", "interview_at", "url"])
    for j in rows:
        writer.writerow([j["title"], j["company"], j["location"], j["score"], j["status"],
                          j["status_updated_at"], j["salary"], j["interview_at"], j["url"]])
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applied_jobs.csv"},
    )


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


@app.post("/api/jobs/{source}/{external_id}/cover-letter")
def cover_letter(source: str, external_id: str):
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
        raise HTTPException(400, "GROQ_API_KEY isn't configured - add it to .env to use cover letters.")
    letter = generate_cover_letter(client, cv_text, job)
    if "error" in letter:
        raise HTTPException(502, letter["error"])
    path = save_cover_letter(job, letter)
    return {**letter, "download_url": f"/cv-notes/{path.name}"}


@app.post("/api/jobs/{source}/{external_id}/apply-kit")
def apply_kit(source: str, external_id: str):
    """Tailored CV + cover letter together, in one call."""
    job = db.get_job(source, external_id)
    if not job:
        raise HTTPException(404, "job not found")
    try:
        cv_text = load_cv()
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    client = _groq_client()
    if client is None:
        raise HTTPException(400, "GROQ_API_KEY isn't configured - add it to .env to use the apply kit.")

    downloads = []
    cv_data = tailor_for_job(client, cv_text, job)
    if "error" not in cv_data:
        path = save_tailored_cv(job, cv_data)
        downloads.append({"label": "Tailored CV", "url": f"/cv-notes/{path.name}"})
    letter = generate_cover_letter(client, cv_text, job)
    if "error" not in letter:
        path = save_cover_letter(job, letter)
        downloads.append({"label": "Cover letter", "url": f"/cv-notes/{path.name}"})

    if not downloads:
        raise HTTPException(502, "Both the CV and cover letter generation failed - try again.")
    return {"downloads": downloads}


@app.get("/api/rejections/analysis")
def rejections_analysis():
    """Looks for genuine patterns across rejected applications."""
    rejected = [j for j in _sorted_jobs() if j["status"] == "rejected"]
    return rejection_insights.analyze_rejections(_groq_client(), rejected)


@app.post("/api/interview")
def interview(body: InterviewMessage):
    """Drives the mock-interview overlay - a separate, tool-free conversation
    loop (interview_agent.py) scoped to growth marketing interview questions.
    Empty history triggers Dextor's opening greeting + first question."""
    try:
        cv_text = load_cv()
    except FileNotFoundError:
        cv_text = None
    reply = interview_agent.interview_turn(_groq_client(), body.history, cv_text)
    return {"reply": reply}


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

    client = _groq_client()

    history = body.history + [{"role": "user", "content": body.message}]
    try:
        reply, downloads = chat_agent.chat(client, history, jobs, cv_text)
    except Exception as e:
        # Belt-and-suspenders: chat_agent.chat() already handles LLM/tool
        # errors gracefully, but a genuinely unexpected bug here shouldn't
        # 500 the request - the chat panel should always get a reply to show.
        return {"reply": f"Something went wrong on my end: {e}", "downloads": []}
    return {"reply": reply, "downloads": downloads}


def _gmail_redirect_uri(request: Request) -> str:
    """Built from the Host header rather than request.url_for, so it works
    whether you're on localhost or a Codespaces forwarded https:// URL -
    it just has to match whatever's registered in Google Cloud Console."""
    host = request.headers.get("host", request.url.hostname)
    scheme = "http" if host.startswith("localhost") or host.startswith("127.0.0.1") else "https"
    return f"{scheme}://{host}/api/gmail/callback"


def _require_gmail():
    if gmail_agent is None:
        raise HTTPException(
            400,
            "Gmail support isn't installed - run `pip install -r requirements-gmail.txt` "
            f"and restart the server to use the Inbox panel. ({GMAIL_IMPORT_ERROR})",
        )


@app.get("/api/gmail/status")
def gmail_status():
    if gmail_agent is None:
        return {"connected": False, "credentials_configured": False}
    return {"connected": gmail_agent.is_connected(), "credentials_configured": gmail_agent.CREDENTIALS_PATH.exists()}


@app.get("/api/gmail/connect")
def gmail_connect(request: Request):
    _require_gmail()
    if not gmail_agent.CREDENTIALS_PATH.exists():
        raise HTTPException(400, "gmail_credentials.json not found - see the Gmail setup section in README.md.")
    flow = gmail_agent.build_auth_flow(_gmail_redirect_uri(request))
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return RedirectResponse(auth_url)


@app.get("/api/gmail/callback")
def gmail_callback(request: Request, code: str | None = None, error: str | None = None):
    _require_gmail()
    if error:
        raise HTTPException(400, f"Google denied access: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code from Google.")
    flow = gmail_agent.build_auth_flow(_gmail_redirect_uri(request))
    flow.fetch_token(code=code)
    gmail_agent.TOKEN_PATH.write_text(flow.credentials.to_json())
    return RedirectResponse("/")


@app.get("/api/gmail/inbox")
def gmail_inbox():
    _require_gmail()
    try:
        service = gmail_agent.get_service()
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    try:
        client = Groq()
    except Exception:
        client = None
    emails = gmail_agent.fetch_recent_emails(service)
    return gmail_agent.classify_importance(client, emails)


app.mount("/cv-notes", StaticFiles(directory=str(CV_SUGGESTIONS_DIR)), name="cv-notes")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
