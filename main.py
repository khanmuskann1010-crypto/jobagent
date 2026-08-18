"""
Phase 2: fetch from France Travail + Adzuna -> drop listings already seen
in a previous run -> score new ones with an LLM -> print ranked results ->
write a styled HTML digest. Scored listings persist in jobs.db, which is
what voice_agent.py and the web dashboard (api.py) both read from - so
anything scored here shows up there immediately.

Usage:
    python main.py
    python main.py --keywords "growth marketing" --max-results 30 --min-score 6

--extra-listings lets another process (e.g. the daily Routine, which pulls
Indeed via Claude's connector since there's no public Indeed API a script
can call directly) feed in pre-fetched listings as a JSON file, so they go
through the same dedupe/score/digest pipeline as France Travail + Adzuna.
Each entry must match the normalize_listing schema: id, source, title,
company, location, description, contract_type, url, date_posted.
"""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

import adzuna
import fetch_jobs
from db import filter_unseen, save_scored
from digest import generate_html
from score_jobs import score_all

DEFAULT_DIGEST_PATH = Path(__file__).parent / "jobs_digest.html"


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Search and rank job listings.")
    parser.add_argument(
        "--keywords",
        default="marketing communication",
        help="Search keywords (default: 'marketing communication')",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=25,
        help="Max listings to fetch per source (default: 25)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Only show listings scoring at or above this (default: 0, show all)",
    )
    parser.add_argument(
        "--digest-path",
        default=str(DEFAULT_DIGEST_PATH),
        help=f"Where to write the HTML digest (default: {DEFAULT_DIGEST_PATH.name})",
    )
    parser.add_argument(
        "--extra-listings",
        default=None,
        help="Path to a JSON file of pre-fetched listings (e.g. Indeed) to merge in",
    )
    args = parser.parse_args()

    print(f"Searching France Travail + Adzuna for '{args.keywords}'...")

    listings = []

    try:
        ft_raw = fetch_jobs.search_jobs(args.keywords, max_results=args.max_results)
        listings += [fetch_jobs.normalize_listing(r) for r in ft_raw]
    except Exception as e:
        print(f"  France Travail fetch failed, skipping this source: {e}")

    try:
        adzuna_raw = adzuna.search_jobs(args.keywords, max_results=args.max_results)
        listings += [adzuna.normalize_listing(r) for r in adzuna_raw]
    except Exception as e:
        print(f"  Adzuna fetch failed, skipping this source: {e}")

    if args.extra_listings:
        extra_path = Path(args.extra_listings)
        if extra_path.exists():
            extra = json.loads(extra_path.read_text())
            listings += extra
            print(f"  Merged {len(extra)} pre-fetched listings from {args.extra_listings}")
        else:
            print(f"  --extra-listings path {args.extra_listings} doesn't exist, skipping it")

    print(f"Fetched {len(listings)} listings across all sources.")

    new_listings = filter_unseen(listings)
    print(f"{len(new_listings)} are new (not seen in a previous run).\n")

    digest_path = Path(args.digest_path)

    if not new_listings:
        print("Nothing new today.")
        generate_html([], digest_path)
        print(f"Digest written to {digest_path}")
        return

    print("Scoring against your profile...\n")
    scored = score_all(new_listings)
    save_scored(scored)

    shown = [s for s in scored if s["score"] >= args.min_score]

    print(f"{'='*70}")
    print(f"RESULTS ({len(shown)} of {len(scored)} shown, ranked by fit)")
    print(f"{'='*70}\n")

    for i, job in enumerate(shown, start=1):
        print(f"[{i}] {job['score']}/10 — {job['title']} @ {job['company']} ({job['source']})")
        print(f"         {job['location']} | {job['contract_type']}")
        print(f"         {job['reason']}")
        if job["url"]:
            print(f"         {job['url']}")
        print()

    generate_html(shown, digest_path)
    print(f"Digest written to {digest_path}")
    print("Saved to jobs.db — use voice_agent.py or the dashboard to talk about these listings and tailor your CV.")


if __name__ == "__main__":
    main()
