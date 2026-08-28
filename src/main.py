"""
Phase 1: fetch -> score -> print, sorted highest fit first.

Usage:
    python -m src.main
    python -m src.main --keywords "growth marketing" --max-results 30

No database, no scheduling yet - that's Phase 2. This just proves the
core loop works end to end.
"""

import argparse
import sys

from src.config import ConfigError, load_config
from src.fetch_jobs import FetchJobsError, normalize_listing, search_jobs
from src.score_jobs import ScoreJobsError, score_all


def _validate_args(keywords: str, max_results: int, min_score: int) -> str | None:
    if not keywords.strip():
        return "--keywords cannot be empty"
    if max_results < 1:
        return f"--max-results must be at least 1, got {max_results}"
    if not (0 <= min_score <= 10):
        return f"--min-score must be between 0 and 10, got {min_score}"
    return None


def run(keywords: str, max_results: int, min_score: int) -> tuple[list[dict], list[dict]]:
    """Returns (all_scored, shown) — shown is scored filtered to >= min_score."""
    config = load_config()

    print(f"Searching France Travail for '{keywords}'...")
    raw_results = search_jobs(keywords, config, max_results=max_results)
    listings = [normalize_listing(r) for r in raw_results]
    print(f"Found {len(listings)} listings. Scoring against your profile...\n")

    if not listings:
        return [], []

    scored = score_all(listings, config)
    shown = [s for s in scored if s["score"] >= min_score]
    return scored, shown


def _print_results(shown: list[dict], total_scored: int) -> None:
    print(f"{'='*70}")
    print(f"RESULTS ({len(shown)} of {total_scored} shown, ranked by fit)")
    print(f"{'='*70}\n")

    for job in shown:
        print(f"[{job['score']}/10] {job['title']} @ {job['company']}")
        print(f"         {job['location']} | {job['contract_type']}")
        print(f"         {job['reason']}")
        if job["url"]:
            print(f"         {job['url']}")
        print()


def main():
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

    error = _validate_args(args.keywords, args.max_results, args.min_score)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)

    try:
        scored, shown = run(args.keywords, args.max_results, args.min_score)
        if not scored:
            print("No listings found - try different keywords.")
            sys.exit(0)

        _print_results(shown, len(scored))

    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except (FetchJobsError, ScoreJobsError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
