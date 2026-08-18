# Job Search Agent — Phase 2 + CV tailoring + voice + dashboard

Fetches marketing/growth job listings from France Travail, Adzuna, and
Indeed, skips anything you've already seen, scores each new listing
against your profile using an LLM, and tracks it through to applied.
On top of the core pipeline: LLM-powered CV tailoring per listing, a
CLI voice interface, and a web dashboard with a chat/voice panel, an
application tracker, and a progress view.

Scoring and CV tailoring run on [Groq's free API](https://console.groq.com)
(`openai/gpt-oss-120b`) by default — no credit card required, unlike the
Anthropic API. If you'd rather use Claude, swap the `groq` client calls in
`score_jobs.py`, `cv_tailor.py`, `voice_agent.py`, and `api.py` back to the
`anthropic` SDK; the code is structured the same way either way.

See `build-plan.md` for the original phased plan.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   Voice mode needs an extra install — see [Voice interface](#voice-interface) below.

2. **Get your API credentials** (all three are free, no card required)
   - Groq API key: https://console.groq.com/keys
   - France Travail client ID/secret: register a free account at
     https://francetravail.io, then subscribe your application to the
     "Offres d'emploi v2" product to get credentials
   - Adzuna app ID/key: register a free account at
     https://developer.adzuna.com to get credentials

3. **Set up your environment**
   ```bash
   cp .env.example .env
   ```
   Then fill in the five values in `.env`.

4. **Edit your profile** (optional, but recommended)
   Open `profile.md` and adjust target roles, deal-breakers, and strengths
   to match how you actually want listings judged.

5. **Fill in your CV** (needed for CV tailoring / voice's "tailor" command)
   Open `cv.md` and replace the placeholder skeleton with your real CV
   content — plain text or markdown is fine, no special formatting needed.

## Run it

```bash
python main.py
```

With options:
```bash
python main.py --keywords "growth marketing" --max-results 30 --min-score 6
```

- `--keywords` — search terms sent to both sources (default: "marketing communication")
- `--max-results` — how many listings to fetch per source (default: 25)
- `--min-score` — only show/digest listings scoring at or above this (default: 0, shows everything)
- `--digest-path` — where to write the HTML digest (default: `jobs_digest.html`)

Each run:
1. Fetches listings from France Travail and Adzuna (a source that fails,
   e.g. missing credentials, is skipped with a warning rather than
   crashing the whole run)
2. Drops anything already recorded in `jobs.db` from a previous run
3. Scores only the new listings with an LLM, against `profile.md`
4. Prints a numbered, ranked list to the terminal
5. Writes `jobs_digest.html` — open it in a browser, or host it (e.g. on
   Netlify) for a daily-review page
6. Saves the run to `last_run.json` — this is what `voice_agent.py` reads,
   and listing numbers (`job 1`, `job 2`, ...) match across the terminal,
   the digest, and voice commands

## CV tailoring

`cv_tailor.py` sends your CV (`cv.md`) plus one job listing to the LLM and
gets back the job's top requirements, how your CV maps to each, 2-4
tailored bullet suggestions, and a tailored opening line for outreach —
written to `cv_suggestions/job_<N>_<company>.md`. It's used by voice mode's
"tailor" command; you can also call it directly:

```python
from groq import Groq
from cv_tailor import load_cv, tailor_for_job, save_suggestions

client = Groq()
cv_text = load_cv()
job = {...}  # a listing dict, e.g. from last_run.json
suggestions = tailor_for_job(client, cv_text, job)
save_suggestions(job, suggestions, index=1)
```

## Voice interface

`voice_agent.py` is a CLI you talk to about your most recent run:

- **"what's new" / "read the digest"** — reads today's scored listings aloud
- **"tell me about job 2"** — reads full details for listing #2
- **"tailor my cv for job 2"** — tailors your CV to listing #2, speaks a
  short summary, writes the full write-up to `cv_suggestions/`
- **"quit" / "exit" / "stop"** — ends the session

Run `python main.py` first so there's a run to talk about, then:

```bash
python voice_agent.py
```

**Setup for spoken mode** (microphone + speakers):
```bash
pip install -r requirements-voice.txt
```
This uses [SpeechRecognition](https://pypi.org/project/SpeechRecognition/)
(Google's free speech-to-text, no API key) to listen and
[pyttsx3](https://pypi.org/project/pyttsx3/) (offline, your OS's built-in
voice) to speak — no paid voice API required. `pyaudio` (needed for mic
access) depends on the native `portaudio` library; see
`requirements-voice.txt` for the one-line install per OS. On Linux, `pyttsx3`
also needs `espeak` installed for speech output.

**No microphone, or just want to try it first?**
```bash
python voice_agent.py --text
```
Same commands, typed instead of spoken, printed instead of read aloud.

## Dashboard

A local web app (FastAPI backend + a single-page frontend) with the job
queue, a chat/voice panel, an applied-jobs tracker, and a progress view —
built around three columns:

- **Left** — the job queue (all scored listings, highest fit first) over
  a progress funnel (new → applied → interviewing → rejected)
- **Center** — chat, typed or spoken (your browser's built-in speech
  recognition/synthesis — Chrome or Edge — no extra install or paid API).
  Same commands as `voice_agent.py`: "what's new", "tell me about job 2",
  "tailor my cv for job 2". Clicking a job in the queue asks about it directly.
- **Right** — your best current match (highest-scoring listing you haven't
  acted on) with a "Mark applied" button, over the applied-jobs tracker

```bash
pip install -r requirements-api.txt -r requirements.txt
uvicorn api:app --reload
```
Then open http://localhost:8000. It reads and writes `jobs.db` directly —
whatever `main.py` (or the daily Routine) has already scored shows up
here, and marking something applied here is what the progress funnel and
Phase 3 tracking are built on.

### API reference

All endpoints are under `/api` and return JSON. `{source}`/`{external_id}`
identify a listing (e.g. `indeed`/`JOBSEARCH_145`).

| Method | Path | Does |
|---|---|---|
| GET | `/api/jobs?min_score=&status=` | List scored jobs, highest score first |
| GET | `/api/jobs/{source}/{external_id}` | One job's full record |
| PATCH | `/api/jobs/{source}/{external_id}/status` | Body `{"status": "applied"}` — one of `new`/`applied`/`interviewing`/`rejected`/`skipped` |
| GET | `/api/applied` | Jobs with status applied/interviewing/rejected |
| GET | `/api/best-match` | Highest-scoring job still at status `new` |
| GET | `/api/progress` | `{total_scored, by_status: {...}}` counts for the funnel |
| POST | `/api/jobs/{source}/{external_id}/tailor-cv` | Runs `cv_tailor.py` against this listing, returns the suggestions |
| POST | `/api/chat` | Body `{"message": "..."}` — same command parsing as `voice_agent.py`, returns `{reply, intent, job_number}` |

Example:
```bash
curl -X PATCH localhost:8000/api/jobs/indeed/JOBSEARCH_145/status \
  -H "Content-Type: application/json" -d '{"status":"applied"}'
```

## Running on a schedule

Use the included wrapper so cron picks up the right working directory:

```bash
crontab -e
```

Add a line to run every morning at 8am:
```
0 8 * * * /full/path/to/job-search-agent/run_daily.sh >> /full/path/to/job-search-agent/cron.log 2>&1
```

## What's next (Phase 3)

- Company career-page watcher for specific target employers
- Chat-driven status updates ("mark job 2 as applied") instead of button-only

## Project structure

```
job-search-agent/
├── profile.md          # your matching criteria — edit this freely
├── cv.md                # your CV content — edit this freely
├── requirements.txt
├── requirements-voice.txt
├── requirements-api.txt
├── .env.example
├── run_daily.sh         # cron wrapper
├── fetch_jobs.py        # France Travail API client
├── adzuna.py            # Adzuna API client
├── indeed_source.py      # parses Claude's Indeed connector output into the common listing schema
├── db.py                # SQLite store: dedup history + application status (jobs.db, tracked in git)
├── digest.py            # styled HTML digest generator
├── score_jobs.py        # LLM scoring logic (Groq by default)
├── cv_tailor.py          # LLM CV-tailoring logic (Groq by default)
├── voice_agent.py        # CLI voice interface
├── api.py                # dashboard backend (FastAPI)
├── frontend/index.html   # dashboard frontend
└── main.py              # orchestrator — run this
```
