"""
Read-only Gmail integration for the dashboard's Inbox panel.

Uses your own free Google Cloud OAuth app (see README's Gmail setup section)
so the dashboard can read your inbox and flag which messages look
job-search-relevant - interview invites, recruiter replies, application
confirmations, rejections - using Groq the same way score_jobs.py judges
listings. Nothing is ever sent or deleted; the OAuth scope is read-only.

The connect flow runs entirely through the dashboard itself (a "Connect
Gmail" button hitting /api/gmail/connect and /api/gmail/callback in api.py)
rather than a local-server OAuth script, since the dashboard commonly runs
in a remote Codespace where a script-opened local browser can't complete
the redirect back to the container.
"""

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from groq import Groq

CREDENTIALS_PATH = Path(__file__).parent / "gmail_credentials.json"
TOKEN_PATH = Path(__file__).parent / "gmail_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MODEL = "openai/gpt-oss-120b"


def is_connected() -> bool:
    return TOKEN_PATH.exists()


def build_auth_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri)


def get_service():
    """Returns an authorized Gmail API client, refreshing the token if needed.
    Raises RuntimeError with a clear, user-facing message if not connected yet
    or the connection has gone stale and needs reconnecting."""
    if not TOKEN_PATH.exists():
        raise RuntimeError("Gmail isn't connected yet - click \"Connect Gmail\" in the Inbox panel.")
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_PATH.read_text()), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            raise RuntimeError("Gmail's connection expired - click \"Connect Gmail\" again to reconnect.")
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_recent_emails(service, max_results: int = 15) -> list[dict]:
    """Most recent inbox messages, newest first - subject/sender/snippet/date/unread,
    no bodies fetched beyond Gmail's own short snippet (keeps this fast and cheap)."""
    resp = service.users().messages().list(userId="me", maxResults=max_results, labelIds=["INBOX"]).execute()
    message_ids = resp.get("messages", [])

    emails = []
    for m in message_ids:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = msg["payload"]["headers"]
        emails.append({
            "id": msg["id"],
            "from": _header(headers, "From"),
            "subject": _header(headers, "Subject") or "(no subject)",
            "snippet": msg.get("snippet", ""),
            "date": _header(headers, "Date"),
            "unread": "UNREAD" in msg.get("labelIds", []),
        })
    return emails


IMPORTANCE_PROMPT = """You triage an inbox for someone actively job-hunting. Given a JSON list of \
emails (id, from, subject, snippet), decide which ones are job-search-relevant - interview \
invitations, recruiter outreach, application confirmations, offers, rejections, assessment/test \
invites - as opposed to newsletters, promotions, unrelated personal mail, etc.

Respond with ONLY a JSON object: {"results": [{"id": "<id>", "important": true|false, "category": \
"<one of: interview, recruiter_outreach, application_confirmation, offer, rejection, assessment, other>"}, ...]} \
- one entry per email given, same ids."""


def classify_importance(client: Groq | None, emails: list[dict]) -> list[dict]:
    """Tags each email with important/category via Groq. Falls back to marking
    everything unclassified (important=None) if no client or the call fails -
    the inbox still renders, just without the job-relevance flag."""
    if not client or not emails:
        for e in emails:
            e["important"] = None
            e["category"] = None
        return emails

    slim = [{"id": e["id"], "from": e["from"], "subject": e["subject"], "snippet": e["snippet"][:200]} for e in emails]
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1500,
            reasoning_effort="low",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": IMPORTANCE_PROMPT},
                {"role": "user", "content": json.dumps(slim, ensure_ascii=False)},
            ],
        )
        parsed = json.loads(response.choices[0].message.content)
        by_id = {r["id"]: r for r in parsed.get("results", [])}
    except Exception:
        by_id = {}

    for e in emails:
        tag = by_id.get(e["id"])
        e["important"] = tag["important"] if tag else None
        e["category"] = tag.get("category") if tag else None
    return emails
