"""
Looks for genuine patterns across your rejected applications - a common
score band, a recurring location/contract mismatch, a gap mentioned
repeatedly in the original fit-score reasons - using Groq, the same way
score_jobs.py judges listings. Only ever reports a pattern the data
actually supports; with too little data it says so instead of guessing.
"""

import json

from groq import Groq

from groq_errors import friendly_groq_error

MODEL = "openai/gpt-oss-120b"
MIN_REJECTED = 3

SYSTEM_PROMPT = """You analyze a job seeker's rejected applications to find genuine patterns \
worth acting on - NOT to guess why any single company rejected them (you don't have that \
information, only the ORIGINAL fit-score reason from before they applied). Given a JSON list of \
rejected listings (title, company, location, contract_type, score, reason), look for real \
patterns across MULTIPLE listings: a common score band, a recurring location/contract mismatch, \
a skill or requirement mentioned repeatedly in low-scoring reasons, etc.

Respond with ONLY a JSON object: {"patterns": ["<pattern 1>", "<pattern 2>", ...], "summary": \
"<one or two sentence overall takeaway>"}. If there's truly no discernible pattern with this few \
data points, say so honestly in "summary" and leave "patterns" empty - never invent a pattern \
that isn't actually supported by the data."""


def analyze_rejections(client: Groq | None, rejected_jobs: list[dict]) -> dict:
    if len(rejected_jobs) < MIN_REJECTED:
        return {
            "error": (
                f"Only {len(rejected_jobs)} rejected so far - need at least {MIN_REJECTED} "
                "before a pattern would mean anything."
            )
        }
    if client is None:
        return {"error": "Groq API key isn't configured - add GROQ_API_KEY to your .env."}

    slim = [
        {
            "title": j["title"], "company": j["company"], "location": j["location"],
            "contract_type": j["contract_type"], "score": j["score"], "reason": j["reason"],
        }
        for j in rejected_jobs
    ]
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=800,
            reasoning_effort="low",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(slim, ensure_ascii=False)},
            ],
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": friendly_groq_error(e)}
