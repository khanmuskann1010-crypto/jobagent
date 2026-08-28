"""
End-to-end loop:

  python -m src.main --company "Acme Corp" --url "https://acme.com" \
      --need "hiring 5 engineers in Paris this quarter"

Produces: proposals/<company>_<date>.docx — a draft for you to review
and edit before sending. Nothing here auto-sends anything.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from src.build_docx import build_docx, safe_filename, unique_output_path
from src.config import CATALOG_PATH, ConfigError, load_config
from src.generate_proposal import ProposalGenerationError, generate_proposal
from src.research import research_company

OUTPUT_DIR = Path(__file__).parent.parent / "proposals"


def _validate_args(company: str, url: str) -> str | None:
    if not company.strip():
        return "Company name cannot be empty"
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return f"--url must be a full http(s) URL, got: {url!r}"
    return None


def run(company: str, url: str, need: str) -> Path:
    config = load_config()

    if not CATALOG_PATH.exists():
        raise ConfigError(
            f"service_catalog.json not found at {CATALOG_PATH}. "
            "Copy/edit the example that ships with this tool, or restore it before running."
        )
    with open(CATALOG_PATH) as f:
        catalog = json.load(f)

    print(f"[1/3] Researching {company}...")
    research = research_company(company, url, need)
    if research.get("fetch_error"):
        print(f"  (warning: couldn't fetch site — {research['fetch_error']}. Continuing with notes only.)")

    print("[2/3] Drafting proposal...")
    proposal = generate_proposal(research, catalog, config)
    if "raw_output" in proposal:
        print("  (warning: model output wasn't valid JSON — raw text will be included in the docx instead.)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = unique_output_path(OUTPUT_DIR, safe_filename(company), date.today().isoformat())

    print(f"[3/3] Writing {out_path}...")
    build_docx(company, proposal, out_path)

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate a draft B2B proposal from a prospect URL + notes.")
    parser.add_argument("--company", required=True, help="Prospect company name")
    parser.add_argument("--url", default="", help="Prospect website URL (http/https)")
    parser.add_argument("--need", default="", help="Free-text notes on what they seem to need")
    args = parser.parse_args()

    error = _validate_args(args.company, args.url)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)

    try:
        out_path = run(args.company, args.url, args.need)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except ProposalGenerationError as e:
        print(f"Proposal generation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        sys.exit(130)

    print(f"\nDone. Review and edit: {out_path}")


if __name__ == "__main__":
    main()
