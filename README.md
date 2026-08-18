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
gets back a tailored version of your actual CV — same roles, companies, and
dates, with the summary/skills/bullets re-emphasized and reworded for that
job — rendered as a one-page PDF at
`cv_suggestions/<source>_<id>_<company>_CV.pdf`. The prompt explicitly
forbids inventing companies, titles, dates, or achievements; it can only
reorder, re-emphasize, and reword what's already in your real CV. It's used
by voice mode's "tailor" command and the dashboard's download link; you can
also call it directly:

```python
from groq import Groq
from cv_tailor import load_cv, tailor_for_job, save_tailored_cv

client = Groq()
cv_text = load_cv()
job = {...}  # a listing dict, e.g. from db.get_all_jobs()
cv_data = tailor_for_job(client, cv_text, job)
save_tailored_cv(job, cv_data)
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

A local web app (FastAPI backend + a single-page frontend, dark theme only)
named Dextor — the job queue, a real conversational assistant, a mock
interview mode, an interview calendar, an applied-jobs tracker, and a
tabbed Insights/LinkedIn/Inbox panel, built around three columns:

- **Left** — your applied-jobs tracker (with a CSV export button) → a
  tabbed panel switching between **Insights** (status funnel, score
  distribution, jobs by source, an applications-over-time trend),
  **LinkedIn** (quick links to your profile/messages/posting plus a notes
  scratchpad saved in your browser), and **Inbox** (recent Gmail messages,
  with job-relevant ones flagged by the same LLM that scores listings) →
  your best current match (highest-scoring listing you haven't acted on)
  with a "Mark applied" button
- **Center** — the Dextor orb (click it to start a mock interview - see
  below; it also reacts visually while thinking/listening/speaking) over
  the job queue (search/filter box on top, matches title, company,
  location, and salary; ranked by fit). Clicking a listing both asks
  Dextor about it and opens the real posting in a new tab.
- **Right** — an interview **Calendar** (compact month view + your next
  few interviews - set a date by asking Dextor, or with the 📅 button on
  an applied row) → Dextor's chat panel. A genuine conversational agent
  (`chat_agent.py`), not a fixed command parser - ask it anything about
  your search, it decides for itself when to look up a job, tailor your
  CV, draft a cover letter, put together a full apply kit (CV + cover
  letter together), mark something applied, schedule an interview, check
  who needs a follow-up, look for patterns across your rejections, or
  check progress, via tool calls. Typed or spoken (your browser's
  built-in speech recognition - Safari or Chrome - no extra install or
  paid API); it only speaks a reply back when you used the mic, and a
  stop button appears while it's talking so you can cut it off.

### Mock interview

Click the Dextor orb (top-center) while it's idle to start a mock
interview - it takes over the full screen, asks one question at a time
(mixing background, scenario/case, metrics, and behavioral questions),
gives brief honest feedback after each answer, and speaks every question
aloud automatically. Scoped specifically to growth marketing interviews -
this app screens listings for that role family, so the questions do too
(`interview_agent.py`, a separate conversation loop from the main chat,
grounded in your real CV). Exit with the ✕, same as anywhere else in the app.

### Focus mode

The 🎯 icon in the header hides everything but the job queue and chat
(plus the calendar), swaps in a red/black theme, and runs a 30-minute
countdown. The same icon exits it - leaving before 30 minutes asks you to
confirm, but never locks you in.

### Groq usage

The 📊 icon in the chat panel toggles today's Groq token usage - useful
since the free tier's daily cap (200k tokens for `openai/gpt-oss-120b`,
shared across scoring/chat/CV tailoring/cover letters/interviews) is easy
to run into without warning. Groq's rate-limit response headers only
cover the per-minute window, and there's no API to query the daily quota
directly, so `groq_usage.py` tracks it locally from two sources: every
successful call's real token count, resynced whenever a 429 daily-limit
error hands back Groq's own exact numbers. This is usage tracked **by
this app**, not Groq's live dashboard - close enough to know if you're
near the limit, not a billing record (see
[console.groq.com/settings/billing](https://console.groq.com/settings/billing)
for that).

Other conveniences: a full screen toggle and an opt-in desktop-notification
bell for strong (8+/10) new matches, both top right; a slim alert banner
under the header when an application could use a follow-up or you have an
interview today; toast confirmations on status changes; a "/" keyboard
shortcut to jump to the chat box; low-score listings nobody's acted on for
30+ days quietly move to "skipped" so the queue stays current; and the
queue/insights/calendar/applied panels auto-refresh every 60 seconds (the
inbox refreshes only when you click its own refresh icon, since each load
costs a Groq call).

```bash
pip install -r requirements-api.txt -r requirements.txt
uvicorn api:app --reload
```
Then open http://localhost:8000. It reads and writes `jobs.db` directly —
whatever `main.py` (or the daily Routine) has already scored shows up
here, and marking something applied here is what the progress funnel and
Phase 3 tracking are built on.

### Gmail setup (optional — for the Inbox panel)

The Inbox panel needs its own free Google Cloud OAuth app, which only you
control — it requests read-only access to your inbox, nothing is ever sent
or deleted. It's entirely optional; without it the panel just shows a
"Connect Gmail" button and everything else works as normal.

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and
   create a new project (free, no billing needed for this).
2. **APIs & Services → Library** → search "Gmail API" → **Enable**.
3. **APIs & Services → OAuth consent screen** → choose **External** → fill
   in an app name and your email → under "Test users", add your own Google
   account email. (Since this is a personal, unverified app, Google may
   expire the connection after about a week — if the Inbox panel stops
   loading, just click "Connect Gmail" again.)
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type **Web application**.
   - Under "Authorized redirect URIs", add the exact URL you use to open
     the dashboard, with `/api/gmail/callback` appended — e.g. if you open
     `https://your-codespace-8000.app.github.dev`, add
     `https://your-codespace-8000.app.github.dev/api/gmail/callback`. If
     you're running locally, add `http://localhost:8000/api/gmail/callback`.
5. Click **Download JSON** on the credential you just created, rename the
   file to `gmail_credentials.json`, and place it in the project root
   (it's gitignored — never commit it).
6. `pip install -r requirements-gmail.txt`, restart the dashboard, and
   click **Connect Gmail** in the Inbox panel — sign in and approve access.
   This saves `gmail_token.json` (also gitignored) and the panel starts
   showing your recent inbox.

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
| GET | `/api/groq-usage` | `{date, used, limit, remaining, pct}` - today's Groq token usage, tracked by this app (see below) |
| POST | `/api/jobs/{source}/{external_id}/tailor-cv` | Runs `cv_tailor.py` against this listing, returns the suggestions |
| POST | `/api/jobs/{source}/{external_id}/cover-letter` | Runs `cover_letter.py` against this listing, returns the letter |
| POST | `/api/jobs/{source}/{external_id}/apply-kit` | Tailored CV + cover letter together, returns `{downloads: [{label, url}, ...]}` |
| PATCH | `/api/jobs/{source}/{external_id}/interview` | Body `{"when": "2026-08-22T14:00:00"}` (or `null` to clear) |
| GET | `/api/follow-ups?days=7` | Applications with no status update in `days` - worth a nudge |
| GET | `/api/calendar` | Jobs with a scheduled interview, soonest first |
| GET | `/api/progress/trend?days=30` | `{dates, series: {applied, interviewing, rejected}}` cumulative counts for the trend chart |
| GET | `/api/rejections/analysis` | Pattern analysis across rejected applications (`rejection_insights.py`), needs 3+ rejections |
| GET | `/api/export/applied.csv` | CSV download of your applied/interviewing/rejected jobs |
| POST | `/api/chat` | Body `{"message": "...", "history": [...]}` — free-form chat with Dextor (`chat_agent.py`), returns `{reply, downloads: [{label, url}, ...]}` |
| POST | `/api/interview` | Body `{"history": [...]}` — drives the mock-interview overlay (`interview_agent.py`); empty history starts a new session |
| GET | `/api/gmail/status` | `{connected, credentials_configured}` |
| GET | `/api/gmail/connect` | Redirects to Google's consent screen |
| GET | `/api/gmail/callback` | OAuth redirect target — saves the token, then redirects back to `/` |
| GET | `/api/gmail/inbox` | Recent inbox messages, each tagged `{important, category}` by Groq |

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
├── requirements-gmail.txt
├── .env.example
├── run_daily.sh         # cron wrapper
├── fetch_jobs.py        # France Travail API client
├── adzuna.py            # Adzuna API client
├── indeed_source.py      # parses Claude's Indeed connector output into the common listing schema
├── db.py                # SQLite store: dedup history + application status (jobs.db, tracked in git)
├── digest.py            # styled HTML digest generator
├── score_jobs.py        # LLM scoring logic (Groq by default)
├── cv_tailor.py          # LLM CV-tailoring logic (Groq by default)
├── cover_letter.py        # LLM cover-letter generation (Groq by default)
├── voice_agent.py        # CLI voice interface
├── api.py                # dashboard backend (FastAPI)
├── chat_agent.py          # tool-using conversational agent for the dashboard chat
├── interview_agent.py     # mock-interview conversation loop (growth marketing)
├── rejection_insights.py  # pattern analysis across rejected applications
├── groq_errors.py         # turns raw Groq API errors into plain-language messages
├── groq_usage.py          # local daily token-usage tracker for the usage toggle
├── gmail_agent.py         # Gmail OAuth + inbox fetch/importance-tagging for the Inbox panel
├── frontend/index.html   # dashboard frontend
└── main.py              # orchestrator — run this
```
