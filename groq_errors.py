"""
Turns Groq's raw API error text into something a non-technical person can
actually read, instead of dumping the SDK's JSON error blob at them - most
commonly hit via the free tier's daily token cap (200k tokens/day for
openai/gpt-oss-120b, shared across scoring, chat, CV tailoring, cover
letters, and mock interviews), which resets on a rolling window rather
than at a fixed time.
"""

import re

_WAIT_RE = re.compile(r"try again in ([\d.]+(?:h)?[\d.]*(?:m)?[\d.]*(?:s)?)", re.IGNORECASE)


def friendly_groq_error(e: Exception) -> str:
    text = str(e)
    if "rate_limit_exceeded" in text or "Rate limit reached" in text:
        wait_match = _WAIT_RE.search(text)
        wait = f" It resets shortly - try again in about {wait_match.group(1)}." if wait_match else " Try again in a few minutes."
        if "tokens per day" in text or "(TPD)" in text:
            return f"Groq's free daily usage limit is used up for now.{wait}"
        return f"Groq's rate limit is maxed out right now.{wait}"
    return f"Something went wrong on my end: {text}"
