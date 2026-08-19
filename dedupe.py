"""
Collapses job listings that are almost certainly the same real posting -
scraped independently by Indeed, Adzuna, France Travail, etc. - into one
card, so the queue doesn't show the same job three times just because three
job boards each listed it separately.

Matching is deliberately conservative: same company (after normalizing
accents/case/punctuation) AND a similar-enough title. Two genuinely
different postings at the same company essentially never share that much
title text, so this rarely over-merges - a missed duplicate is a much
smaller problem than two real jobs getting wrongly folded into one card.
"""

import re
import unicodedata
from difflib import SequenceMatcher

TITLE_SIMILARITY_THRESHOLD = 0.62


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _same_posting(a: dict, b: dict) -> bool:
    if _normalize(a["company"]) != _normalize(b["company"]):
        return False
    return SequenceMatcher(None, _normalize(a["title"]), _normalize(b["title"])).ratio() >= TITLE_SIMILARITY_THRESHOLD


def group_duplicates(jobs: list[dict]) -> list[dict]:
    """jobs should already be score-sorted. Groups same-posting listings
    together; within a group, a listing you've actually acted on (status
    != "new") becomes the primary card regardless of score, so you never
    lose track of something you've already applied to just because a
    higher-scoring duplicate showed up from another source. The rest are
    attached as also_seen_on and dropped from the top-level list."""
    groups: list[list[dict]] = []
    for job in jobs:
        target = next((g for g in groups if _same_posting(g[0], job)), None)
        if target is not None:
            target.append(job)
        else:
            groups.append([job])

    merged = []
    for group in groups:
        acted_on = [j for j in group if j["status"] != "new"]
        primary = acted_on[0] if acted_on else group[0]
        others = [j for j in group if j is not primary]
        merged.append({
            **primary,
            "also_seen_on": [{"source": o["source"], "url": o["url"]} for o in others],
        })
    merged.sort(key=lambda j: j["score"], reverse=True)
    return merged
