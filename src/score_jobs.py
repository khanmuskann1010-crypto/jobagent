"""
Uses the Claude API to score each job listing against profile.md.

Returns a fit score (1-10) and a one-line reason per listing, so results
can be ranked before you spend time reading full descriptions yourself.
"""

import json
import re
import time
from pathlib import Path

import anthropic

from src.config import Config

PROFILE_PATH = Path(__file__).parent.parent / "profile.md"

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

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ScoreJobsError(Exception):
    """Raised when profile.md is missing/unreadable."""


def load_profile() -> str:
    if not PROFILE_PATH.exists():
        raise ScoreJobsError(
            f"profile.md not found at {PROFILE_PATH} — this file is required "
            "context for scoring; see profile.md in the repo for the expected format."
        )
    text = PROFILE_PATH.read_text().strip()
    if not text:
        raise ScoreJobsError(f"profile.md at {PROFILE_PATH} is empty.")
    return text


def _extract_json(raw_text: str) -> dict:
    cleaned = _JSON_FENCE_RE.sub("", raw_text.strip()).strip()
    return json.loads(cleaned)


def score_listing(client: anthropic.Anthropic, profile: str, listing: dict, config: Config) -> dict:
    """Score a single normalized listing dict (from fetch_jobs.normalize_listing)."""
    user_content = f"""CANDIDATE PROFILE:
{profile}

JOB LISTING:
Title: {listing['title']}
Company: {listing['company']}
Location: {listing['location']}
Contract type: {listing['contract_type']}
Description: {listing['description'][:2000]}"""

    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw_text = response.content[0].text.strip() if response.content else ""

            try:
                parsed = _extract_json(raw_text)
                return {"score": int(parsed["score"]), "reason": str(parsed["reason"])}
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                # Don't retry a parse failure — it's not a transient API issue, just
                # flag it so one bad response doesn't crash the whole batch.
                return {"score": 0, "reason": f"Could not parse model response: {raw_text[:100]}"}

        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            last_error = e
            if attempt < config.max_retries:
                time.sleep(min(2**attempt, 10))
                continue
        except anthropic.AuthenticationError as e:
            # Not worth retrying, and not worth silently scoring 0 either — a bad key
            # means every remaining listing will fail the same way.
            raise ScoreJobsError(
                "Anthropic API rejected the API key — check ANTHROPIC_API_KEY in your .env"
            ) from e
        except anthropic.APIStatusError as e:
            last_error = e
            break

    return {"score": 0, "reason": f"Scoring failed after retries: {last_error}"}


def score_all(listings: list[dict], config: Config) -> list[dict]:
    """Score a batch of listings, attaching score + reason to each, sorted highest first."""
    if not listings:
        return []

    client = anthropic.Anthropic(api_key=config.anthropic_api_key, timeout=config.request_timeout)
    profile = load_profile()

    scored = []
    for listing in listings:
        result = score_listing(client, profile, listing, config)
        scored.append({**listing, **result})

    return sorted(scored, key=lambda x: x["score"], reverse=True)
