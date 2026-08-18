"""
Uses Groq's free API (openai/gpt-oss-120b) to score each job listing
against profile.md.

Returns a fit score (1-10) and a one-line reason per listing, so results
can be ranked before you spend time reading full descriptions yourself.
"""

import json
from pathlib import Path

from groq import Groq

PROFILE_PATH = Path(__file__).parent / "profile.md"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are screening job listings for one specific candidate.
You will be given the candidate's profile and criteria, then a single job
listing. Score how well this listing fits the candidate.

Respond with ONLY a JSON object, no other text, no markdown fences:
{"score": <integer 1-10>, "reason": "<one sentence, plain language>"}

Score 1-3: clear mismatch (wrong level, wrong location, deal-breaker present)
Score 4-6: partial fit, worth a second look but not a priority
Score 7-10: strong fit, surface this prominently

Be honest and specific in the reason - name the actual factor that drove
the score (e.g. "Senior title matches but requires native French" rather
than a vague "seems like a good fit")."""


def load_profile() -> str:
    return PROFILE_PATH.read_text()


def score_listing(client: Groq, profile: str, listing: dict) -> dict:
    """Score a single normalized listing dict (from fetch_jobs.normalize_listing)."""
    user_content = f"""CANDIDATE PROFILE:
{profile}

JOB LISTING:
Title: {listing['title']}
Company: {listing['company']}
Location: {listing['location']}
Contract type: {listing['contract_type']}
Description: {listing['description'][:2000]}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            reasoning_effort="low",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as e:
        # gpt-oss-120b occasionally burns its whole token budget on hidden
        # reasoning and returns nothing, which Groq rejects outright - don't
        # let one bad listing take down the rest of the batch
        return {"score": 0, "reason": f"Scoring failed for this listing: {e}"}

    try:
        parsed = json.loads(raw_text)
        return {"score": int(parsed["score"]), "reason": parsed["reason"]}
    except (json.JSONDecodeError, KeyError, ValueError):
        # If the model's output didn't parse cleanly, don't crash the whole run -
        # just flag it so you can see something went wrong for this listing
        return {"score": 0, "reason": f"Could not parse model response: {raw_text[:100]}"}


def score_all(listings: list[dict]) -> list[dict]:
    """Score a batch of listings, attaching score + reason to each, sorted highest first."""
    client = Groq()  # reads GROQ_API_KEY from env
    profile = load_profile()

    scored = []
    for listing in listings:
        result = score_listing(client, profile, listing)
        scored.append({**listing, **result})

    return sorted(scored, key=lambda x: x["score"], reverse=True)
