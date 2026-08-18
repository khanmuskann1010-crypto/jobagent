"""
Conversational agent for the dashboard's chat panel.

Unlike a fixed command parser, this lets the LLM hold a real conversation
and decide for itself when it needs real data - listing the queue, pulling
one job's full details, tailoring a CV, updating an application status, or
checking progress - via tool calls, the same pattern an agent like Claude
uses. You can ask it anything; it only reaches for a tool when it actually
needs one.
"""

import json

from groq import Groq

import db
from cv_tailor import save_tailored_cv, tailor_for_job

MODEL = "openai/gpt-oss-120b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_jobs",
            "description": (
                "List jobs in the queue, ranked by fit score (highest first). "
                "Job numbers here match what's shown in the app's UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_score": {
                        "type": "integer",
                        "description": "Only include jobs scoring at least this (0-10). Omit for all.",
                    },
                    "status": {
                        "type": "string",
                        "enum": list(db.STATUSES),
                        "description": "Only include jobs with this application status. Omit for all.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": "Get full details for one job by its queue number - title, company, location, score, reason, status, and description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_number": {"type": "integer", "description": "1-indexed position in the queue"},
                },
                "required": ["job_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tailor_cv",
            "description": (
                "Generate a tailored version of the candidate's actual CV for one specific job, "
                "as a downloadable PDF. Only call this when the user actually asks to tailor/adapt "
                "their CV or resume for a job - it takes real time, don't call it speculatively."
            ),
            "parameters": {
                "type": "object",
                "properties": {"job_number": {"type": "integer"}},
                "required": ["job_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_status",
            "description": "Mark a job's application status - e.g. when the user says they applied, got an interview, or were rejected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_number": {"type": "integer"},
                    "status": {"type": "string", "enum": list(db.STATUSES)},
                },
                "required": ["job_number", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": "Get counts of jobs by application status (new/applied/interviewing/rejected/skipped) across the whole queue.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are a warm, sharp, conversational job-search assistant helping one \
candidate manage their job search. You're talking to them directly, like a knowledgeable \
friend who's on top of their applications - not a command-line tool. Have a real conversation: \
answer questions, share honest opinions on listings, make small talk if they do, ask a \
clarifying question when something's ambiguous rather than guessing.

You have tools to list the job queue, get full details on one job, tailor the candidate's CV \
for a job, update a job's application status, and check overall progress. Use them whenever you \
need real data - never guess or invent job details, scores, or statuses. Job numbers refer to \
position in the queue as currently ranked (1 = best fit), matching the numbers shown in the \
app's UI, so "job 3" and "the third one" mean the same thing.

Keep replies conversational and reasonably brief, like a chat message, not a report. Don't dump \
the full job list unless asked for one."""


def _job_summary(job: dict, index: int) -> dict:
    return {
        "job_number": index,
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "score": job["score"],
        "status": job["status"],
        "source": job["source"],
    }


def _execute_tool(
    name: str, args: dict, jobs: list[dict], client: Groq, cv_text: str | None
) -> tuple[dict, str | None]:
    """Returns (result_to_hand_back_to_the_model, download_url_if_any)."""
    if name == "list_jobs":
        min_score = args.get("min_score")
        status = args.get("status")
        rows = [
            _job_summary(j, i)
            for i, j in enumerate(jobs, start=1)
            if (min_score is None or j["score"] >= min_score)
            and (not status or j["status"] == status)
        ]
        return {"jobs": rows}, None

    if name == "get_job_details":
        n = args.get("job_number")
        if not n or not (1 <= n <= len(jobs)):
            return {"error": f"No job number {n} - the queue has {len(jobs)} jobs."}, None
        job = jobs[n - 1]
        return {
            "job_number": n,
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "score": job["score"],
            "reason": job["reason"],
            "status": job["status"],
            "url": job.get("url", ""),
            "description": (job.get("description") or "")[:1500],
        }, None

    if name == "tailor_cv":
        n = args.get("job_number")
        if not n or not (1 <= n <= len(jobs)):
            return {"error": f"No job number {n} - the queue has {len(jobs)} jobs."}, None
        if not cv_text:
            return {"error": "No CV on file - the candidate needs to fill in cv.md first."}, None
        job = jobs[n - 1]
        cv_data = tailor_for_job(client, cv_text, job)
        if "error" in cv_data:
            return {"error": cv_data["error"]}, None
        path = save_tailored_cv(job, cv_data)
        return {"ok": True, "job_number": n, "roles_included": len(cv_data.get("experience", []))}, f"/cv-notes/{path.name}"

    if name == "update_status":
        n = args.get("job_number")
        status = args.get("status")
        if not n or not (1 <= n <= len(jobs)):
            return {"error": f"No job number {n} - the queue has {len(jobs)} jobs."}, None
        if status not in db.STATUSES:
            return {"error": f"status must be one of {db.STATUSES}"}, None
        job = jobs[n - 1]
        db.update_status(job["source"], job["id"], status)
        return {"ok": True, "job_number": n, "status": status}, None

    if name == "get_progress":
        return db.get_progress_stats(), None

    return {"error": f"unknown tool {name}"}, None


def chat(
    client: Groq | None,
    history: list[dict],
    jobs: list[dict],
    cv_text: str | None,
    max_rounds: int = 5,
) -> tuple[str, str | None]:
    """history is [{"role": "user"|"assistant", "content": str}, ...] - prior turns,
    NOT including a system prompt. Returns (reply_text, download_url_or_None)."""
    if client is None:
        return (
            "I'd love to chat, but my Groq API key isn't set up yet — add GROQ_API_KEY to your .env and I'll be ready.",
            None,
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    download_url = None

    for _ in range(max_rounds):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                max_tokens=1200,
                reasoning_effort="low",
            )
        except Exception as e:
            return f"Something went wrong on my end: {e}", download_url

        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or "...", download_url

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result, dl = _execute_tool(tc.function.name, args, jobs, client, cv_text)
            if dl:
                download_url = dl
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return "I got a bit stuck working through that — could you try rephrasing?", download_url
