"""
Phase 1: fetch -> score -> print, sorted highest fit first.

Usage:
    python -m src.main
    python -m src.main --keywords "growth marketing" --max-results 30

No database, no scheduling yet - that's Phase 2. This just proves the
core loop works end to end.
"""

import argparse

from dotenv import load_dotenv

from src.fetch_jobs import normalize_listing, search_jobs
from src.score_jobs import score_all


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
        help="Max listings to fetch and score (default: 25)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Only show listings scoring at or above this (default: 0, show all)",
    )
    args = parser.parse_args()

    print(f"Searching France Travail for '{args.keywords}'...")
    raw_results = search_jobs(args.keywords, max_results=args.max_results)
    listings = [normalize_listing(r) for r in raw_results]
    print(f"Found {len(listings)} listings. Scoring against your profile...\n")

    if not listings:
        print("No listings found - try different keywords.")
        return

    scored = score_all(listings)
    shown = [s for s in scored if s["score"] >= args.min_score]

    print(f"{'='*70}")
    print(f"RESULTS ({len(shown)} of {len(scored)} shown, ranked by fit)")
    print(f"{'='*70}\n")

    for job in shown:
        print(f"[{job['score']}/10] {job['title']} @ {job['company']}")
        print(f"         {job['location']} | {job['contract_type']}")
        print(f"         {job['reason']}")
        if job["url"]:
            print(f"         {job['url']}")
        print()


if __name__ == "__main__":
    main()
