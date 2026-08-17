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
