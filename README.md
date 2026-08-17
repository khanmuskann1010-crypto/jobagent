# Job Search Agent — Phase 2 + CV tailoring + voice

Fetches marketing/growth job listings from the France Travail and Adzuna
APIs, skips anything you've already seen in a previous run, scores each
new listing against your profile using Claude, and produces both a
terminal ranking and a styled HTML digest — highest fit first. On top of
that: Claude-powered CV tailoring per listing, and a voice interface you
can talk to about your results.

See `build-plan.md` for the original phased plan.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   Voice mode needs an extra install — see [Voice interface](#voice-interface) below.

2. **Get your API credentials**
   - Anthropic API key: https://console.anthropic.com/settings/keys
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
3. Scores only the new listings with Claude, against `profile.md`
4. Prints a numbered, ranked list to the terminal
5. Writes `jobs_digest.html` — open it in a browser, or host it (e.g. on
   Netlify) for a daily-review page
6. Saves the run to `last_run.json` — this is what `voice_agent.py` reads,
   and listing numbers (`job 1`, `job 2`, ...) match across the terminal,
   the digest, and voice commands

## CV tailoring

`cv_tailor.py` sends your CV (`cv.md`) plus one job listing to Claude and
gets back the job's top requirements, how your CV maps to each, 2-4
tailored bullet suggestions, and a tailored opening line for outreach —
written to `cv_suggestions/job_<N>_<company>.md`. It's used by voice mode's
"tailor" command; you can also call it directly:

```python
import anthropic
from cv_tailor import load_cv, tailor_for_job, save_suggestions

client = anthropic.Anthropic()
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

- Application tracker: mark listings as applied/interviewing/rejected
- Indeed as a third source
- Company career-page watcher for specific target employers

## Project structure

```
job-search-agent/
├── profile.md          # your matching criteria — edit this freely
├── cv.md                # your CV content — edit this freely
├── requirements.txt
├── requirements-voice.txt
├── .env.example
├── run_daily.sh         # cron wrapper
├── fetch_jobs.py        # France Travail API client
├── adzuna.py            # Adzuna API client
├── db.py                # SQLite dedup store (jobs.db, gitignored)
├── digest.py            # styled HTML digest generator
├── score_jobs.py        # Claude scoring logic
├── cv_tailor.py          # Claude CV-tailoring logic
├── voice_agent.py        # CLI voice interface
└── main.py              # orchestrator — run this
```
