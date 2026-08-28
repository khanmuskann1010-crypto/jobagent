# Proposal Tool

Give it a prospect company + a note on what they need, and it drafts a
B2B services proposal you can review and send: research the prospect's
public site, match them to the right service(s) in your catalog, apply
your pricing rules, and write the prose — output as a `.docx` draft.

This is a separate tool from the job-search agent elsewhere in this repo
— it drafts outbound sales proposals for a services business, rather than
scoring inbound job listings for a candidate.

## What it does

1. **Research** (`src/research.py`) — fetches the prospect's public
   website (homepage + About page if found) as context. No LinkedIn or
   enrichment lookups — those would need separate ToS-compliant
   integrations and are out of scope here.
2. **Generate** (`src/generate_proposal.py`) — sends that research plus
   your `service_catalog.json` to Claude, which matches the prospect to
   the right service(s) and drafts the proposal. Pricing is grounded in
   *your* catalog, not invented by the model.
3. **Output** (`src/build_docx.py` via `src/main.py`) — writes a `.docx`
   draft to `proposals/`.

Nothing auto-sends. Every output is a draft for you to edit.

## Setup

```bash
cd proposal-tool
pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and set `ANTHROPIC_API_KEY` (get one at
https://console.anthropic.com/settings/keys).

## Before your first real run

**`service_catalog.json` ships with pricing grounded in cited market
research**, not invented numbers — six services typical of a B2B
recruitment/staffing + back-office consultancy (retained search,
contingency recruitment, RPO, back-office-as-a-service, employer
branding, fractional TA consulting). Each service carries a
`market_benchmark` note and the catalog's `pricing_research` block lists
the 8 sources used (France-specific data where available, since this is
scoped for a Paris-based consultancy) — see that block for the full
citation list and methodology, retrieved 2026-08-28. One figure
(the employer branding sprint) is flagged as a triangulated estimate
rather than a directly-sourced number, since no source quotes pricing for
that narrow a scope.

**This is still benchmark data, not your firm's real rate card — replace
it with your actual services, prices, and pricing rules before sending
anything to a real prospect.** This file is the whole ballgame, the tool
is only as good as what's in here. Keep the same shape (`service_id`,
`service_name`, `base_price_eur`, `pricing_rules`, `good_fit_for`,
`description`) since the prompt and validation in `generate_proposal.py`
depend on it — `market_benchmark` and `pricing_research` are extra
context for whoever's reviewing drafts and aren't read by the model
prompt, so you're free to drop them once you swap in real pricing.

## Run it

```bash
python -m src.main --company "Acme Corp" --url "https://acme.com" \
    --need "opening a Paris office, hiring 5-10 people this year"
```

Output: `proposals/Acme_Corp_2026-08-28.docx` (a `_2`, `_3`, ... suffix is
added automatically if you run it twice for the same company on the same
day, so an earlier draft is never silently overwritten).

## Configuration

All optional, set in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `PROPOSAL_TOOL_MODEL` | `claude-sonnet-5` | Model used to draft proposals |
| `PROPOSAL_TOOL_TIMEOUT` | `30` | Anthropic API request timeout (seconds) |
| `PROPOSAL_TOOL_MAX_RETRIES` | `3` | Retries on transient API errors (connection/rate-limit/5xx), with exponential backoff |

## Error handling

- Missing `ANTHROPIC_API_KEY` or a malformed `service_catalog.json` fails
  fast with a clear message before any network call.
- A bad or unreachable `--url` doesn't stop the run — research continues
  with just your `--need` notes, and a warning is printed.
- Website fetches are capped (10s timeout, 5MB response size, `http`/`https`
  only, HTML content-type only) so a slow, huge, or malicious page can't
  hang the tool.
- Transient Anthropic API errors (connection issues, rate limits, 5xx) are
  retried automatically; auth errors and other 4xx fail immediately with a
  clear message instead of retrying pointlessly.
- If the model's output isn't valid JSON, the raw text is dumped into the
  doc instead of silently failing — check for a "Raw model output" section
  if something looks off.

## Tests

```bash
pip install pytest
python -m pytest proposal-tool/tests -v
```

Tests mock all network/API calls — no `ANTHROPIC_API_KEY` or internet
access is needed to run them.

## Known limitations (intentional, not bugs)

- Research is website-only — no LinkedIn, Crunchbase, or news lookup
- Pricing logic is whatever you write in plain English in
  `pricing_rules` — the model applies it, it doesn't invent new logic
- No CRM integration, no send step, no multi-user support
- CLI only — no web UI

## How to validate this is worth using regularly

Run it against 5 real prospects (past or current) and compare the draft
to what you'd actually send. The metric that matters at this stage is
**time saved to first draft**, not whether the price is exactly right —
that's what "gaps to confirm" is for.
