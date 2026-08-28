# Job Search Agent — Phase 1

Fetches marketing/growth job listings from the France Travail API, scores
each one against your profile using Claude, and prints a ranked list —
highest fit first.

This is deliberately minimal: no database, no scheduling, no digest page
yet. It proves the core loop (fetch → score → rank) works before adding
anything else. See `job-search-agent-build-plan.md` for what Phase 2 and 3
look like.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Get your API credentials**
   - Anthropic API key: https://console.anthropic.com/settings/keys
   - France Travail client ID/secret: register a free account at
     https://francetravail.io, then subscribe your application to the
     "Offres d'emploi v2" product to get credentials

3. **Set up your environment**
   ```bash
   cp .env.example .env
   ```
   Then fill in the three values in `.env`.

4. **Edit your profile** (optional, but recommended)
   Open `profile.md` and adjust target roles, deal-breakers, and strengths
   to match how you actually want listings judged.

## Run it

```bash
python -m src.main
```

With options:
```bash
python -m src.main --keywords "growth marketing" --max-results 30 --min-score 6
```

- `--keywords` — search terms sent to France Travail (default: "marketing communication")
- `--max-results` — how many listings to fetch and score (default: 25)
- `--min-score` — only print listings scoring at or above this (default: 0, shows everything)

## Configuration

All optional, set in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `JOB_AGENT_MODEL` | `claude-sonnet-5` | Model used to score listings |
| `JOB_AGENT_TIMEOUT` | `15` | Per-request timeout (seconds) for both France Travail and Anthropic calls |
| `JOB_AGENT_MAX_RETRIES` | `3` | Retries on transient errors (connection issues, rate limits, 5xx), with exponential backoff |

## Error handling

- Missing `ANTHROPIC_API_KEY` / `FRANCE_TRAVAIL_CLIENT_ID` / `FRANCE_TRAVAIL_CLIENT_SECRET` fails fast, listing every missing variable, before any network call.
- France Travail OAuth token is cached in memory (with a 30s early-refresh buffer) so a run doesn't re-authenticate on every request.
- Transient network errors (timeouts, connection errors, 5xx) on both APIs are retried automatically with backoff; a bad Anthropic API key stops the run immediately rather than silently scoring every listing 0.
- A single listing that fails to score (malformed model output, exhausted retries) is scored `0` with the reason recorded, so it doesn't crash the rest of the batch.
- Invalid `--keywords` / `--max-results` / `--min-score` are rejected with a clear message before any API calls are made.

## Tests

```bash
pip install pytest
python -m pytest tests -v
```

Tests mock all network/API calls — no credentials or internet access needed.

## What's next (Phase 2)

- Add a second source (Adzuna)
- Store results in SQLite so you don't see the same listing twice
- Generate a styled HTML digest instead of terminal output
- Run on a schedule (cron) instead of manually

## Project structure

```
job-search-agent/
├── profile.md              # your matching criteria — edit this freely
├── requirements.txt
├── .env.example
├── src/
│   ├── fetch_jobs.py        # France Travail API client
│   ├── score_jobs.py        # Claude scoring logic
│   └── main.py               # orchestrator — run this
```
