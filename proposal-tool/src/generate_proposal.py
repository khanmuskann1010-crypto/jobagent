"""
Step 2: turn (research + service catalog) into a draft proposal.

Rules-based pricing lives in service_catalog.json — the model's job is to
(a) match the prospect to the right service(s), (b) apply the stated
pricing_rules, and (c) write the prose. It is explicitly told not to
invent prices outside the catalog.
"""

import json
import re
import time

import anthropic

from src.config import Config

SYSTEM_PROMPT = """You are a proposal-drafting assistant for a B2B services company.

You will be given:
1. Research notes on a prospect company
2. The company's service catalog and pricing rules (JSON)

Your job:
- Identify which 1-2 services from the catalog best fit this prospect, based on the "good_fit_for" signals and what the research tells you about the prospect
- Apply the stated pricing_rules to select the right price/tier — do NOT invent a price that isn't grounded in base_price_eur and the stated adjustment logic
- Draft a short, professional proposal: a one-paragraph situation summary, the recommended service(s) with a one-line rationale each, indicative pricing, and a clear next step
- If the research is thin, say so plainly in a "gaps_to_confirm" note rather than guessing at facts about the prospect
- Keep it tight — this is a draft for the account owner to review and edit before sending, not a final client-facing document

Output valid JSON only, matching this shape:
{
  "situation_summary": "...",
  "recommended_services": [
    {"service_id": "...", "service_name": "...", "rationale": "...", "indicative_price": "..."}
  ],
  "next_step": "...",
  "gaps_to_confirm": ["..."]
}
"""

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

REQUIRED_CATALOG_KEYS = {"services"}
EXPECTED_PROPOSAL_KEYS = {
    "situation_summary",
    "recommended_services",
    "next_step",
    "gaps_to_confirm",
}


class ProposalGenerationError(Exception):
    """Raised when the model call fails after retries, or the catalog is malformed."""


def validate_catalog(catalog: dict) -> None:
    if not isinstance(catalog, dict) or not catalog.get("services"):
        raise ProposalGenerationError(
            "service_catalog.json must contain a non-empty 'services' list. "
            "See service_catalog.json for the expected shape."
        )
    for i, svc in enumerate(catalog["services"]):
        missing = {"service_id", "service_name", "base_price_eur"} - svc.keys()
        if missing:
            raise ProposalGenerationError(
                f"service_catalog.json services[{i}] is missing required field(s): {sorted(missing)}"
            )


def _extract_json(raw_text: str) -> dict:
    cleaned = _JSON_FENCE_RE.sub("", raw_text.strip()).strip()
    return json.loads(cleaned)


def _normalize_proposal(parsed: dict) -> dict:
    """Fill in any keys the model omitted so downstream code never KeyErrors."""
    return {
        "situation_summary": parsed.get("situation_summary", ""),
        "recommended_services": parsed.get("recommended_services", []) or [],
        "next_step": parsed.get("next_step", ""),
        "gaps_to_confirm": parsed.get("gaps_to_confirm", []) or [],
    }


def generate_proposal(research: dict, catalog: dict, config: Config) -> dict:
    validate_catalog(catalog)

    client = anthropic.Anthropic(api_key=config.anthropic_api_key, timeout=config.request_timeout)

    user_content = json.dumps({"research": research, "catalog": catalog}, indent=2)

    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw_text = response.content[0].text if response.content else ""
            if not raw_text.strip():
                raise ProposalGenerationError("Model returned an empty response")

            try:
                parsed = _extract_json(raw_text)
            except json.JSONDecodeError:
                # Fail soft on parse errors: hand back the raw text so nothing is silently
                # lost, but don't retry — a malformed-JSON response is unlikely to be a
                # transient API issue, so retrying just burns tokens for the same result.
                return {
                    "situation_summary": "",
                    "recommended_services": [],
                    "next_step": "",
                    "gaps_to_confirm": ["Model output was not valid JSON — see raw_output"],
                    "raw_output": raw_text,
                }

            return _normalize_proposal(parsed)

        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            last_error = e
            if attempt < config.max_retries:
                time.sleep(min(2 ** attempt, 10))
                continue
        except anthropic.AuthenticationError as e:
            raise ProposalGenerationError(
                "Anthropic API rejected the API key — check ANTHROPIC_API_KEY in your .env"
            ) from e
        except anthropic.APIStatusError as e:
            raise ProposalGenerationError(f"Anthropic API error ({e.status_code}): {e.message}") from e

    raise ProposalGenerationError(
        f"Failed to generate proposal after {config.max_retries} attempts: {last_error}"
    )


if __name__ == "__main__":
    import sys

    from src.config import load_config

    if len(sys.argv) < 2:
        print("Usage: python -m src.generate_proposal <research_json_file>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        research_data = json.load(f)

    with open("service_catalog.json") as f:
        catalog_data = json.load(f)

    result = generate_proposal(research_data, catalog_data, load_config())
    print(json.dumps(result, indent=2))
