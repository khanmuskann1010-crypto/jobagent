# Personal Job Search Agent — Build Plan

**Owner:** Muskan K.
**Goal:** An AI agent, powered by Claude, that searches, ranks, and surfaces relevant marketing/growth roles in France (Paris-focused), so job hunting becomes a daily 5-minute review instead of manual searching across multiple boards.

This is a plan to hand to **Claude Code** to build. It's scoped in phases so you get something usable fast, then layer on complexity.

---

## 1. What this agent actually does

Not a chatbot you talk to — a background worker that:
1. Pulls new job listings from a few real sources on a schedule
2. Reads each listing with Claude and scores it against your profile
3. Filters out noise (irrelevant seniority, wrong location, duplicate postings)
4. Produces a ranked daily/weekly digest — visually, in your own branding
5. (Later) Tracks which ones you've applied to, so nothing falls through

---

## 2. Data sources (the part most plans get wrong)

LinkedIn has no public search API for third-party apps — scraping it violates their Terms of Service and is not a safe foundation to build on. Skip it as a direct source.

Use official, legal sources instead:

| Source | Why | Notes |
|---|---|---|
| **France Travail (ex–Pôle Emploi) API** | Official French government job board, huge coverage, free, public API | Best primary source for France-based roles — requires free API key registration |
| **Adzuna API** | Aggregates listings across many boards, has a France endpoint, free tier | Good secondary source, easy REST API |
| **Indeed** | Already connected as a tool in this chat | Good for cross-checking / broader net beyond France-only sources |
| Company career pages (later phase) | For target companies you specifically want (e.g. EdTech, AdTech, agencies) | Needs simple scraping per-site, lower priority — do this only after the core loop works |

**Phase 1 rule of thumb:** wire up just France Travail + Adzuna. Two sources is enough to validate the whole pipeline before adding more.

---

## 3. Architecture overview

```
[Scheduler: daily cron]
        │
        ▼
[Fetch jobs from France Travail API + Adzuna API]
        │
        ▼
[Dedup against previously-seen listings] ── (store in local DB/JSON)
        │
        ▼
[Claude API: score + summarize each new listing]
   — reads job description
   — compares against your profile/criteria doc
   — outputs: fit score (1-10), one-line reason, flags (seniority mismatch, salary, etc.)
        │
        ▼
[Rank + filter: keep score ≥ threshold]
        │
        ▼
[Generate digest — HTML page or artifact, styled in your emerald/gold brand]
        │
        ▼
[You review — mark "interested" / "skip" / "applied"]
```

The Claude API calls are the "agent" part — everything else is plumbing.

---

## 4. Your matching profile (feed this to Claude as context)

Write a `profile.md` the agent reads on every run — this is what Claude scores listings against. Base it on what's already in your portfolio:

- Target roles: Marketing Communications, Growth Marketing, Marketing Project Management
- Level: Manager/Lead level (not entry-level — 5 years across DeltaX, Kraftshala, L2R Partners)
- Location: Paris, France (open to hybrid/remote within France)
- Language: comfortable in English-speaking roles; note French proficiency level if relevant, since many Paris marketing roles require French
- Industries you've worked in: EdTech, AdTech, B2B services/recruiting — flag strong matches here
- Deal-breakers: e.g. pure sales roles, junior individual-contributor titles, non-Paris relocation required

Keeping this as an editable file (not hardcoded) means you can tune it without touching code.

---

## 5. Build phases

**Phase 1 — Prove the loop (aim: 1–2 days of Claude Code work)**
- Single script, run manually
- Pull from France Travail API only
- Claude scores each listing against a hardcoded version of your profile
- Output: a plain markdown list, sorted by score
- No storage, no dedup yet — just prove fetch → score → rank works end to end

**Phase 2 — Make it usable daily**
- Add Adzuna as a second source
- Add a local SQLite/JSON store so you don't see the same listing twice
- Add the visual digest — a styled HTML page (reuse your portfolio's emerald/gold system) instead of plain markdown
- Add a cron job or scheduled task so it runs automatically each morning

**Phase 3 — Make it a real tool**
- Application tracker: mark listings as applied/interviewing/rejected, stored persistently
- Optional: Claude drafts a tailored outreach note or cover-letter opener per listing you mark "interested," using your career details as context
- Optional: Indeed added as a third source for broader coverage
- Optional: simple company-page watcher for 5–10 target employers you care about specifically

Don't start Phase 3 before Phase 1 and 2 are working reliably — the scoring quality matters more than the number of sources.

---

## 6. Tech stack recommendation

- **Language:** Python (simplest for API calls + scheduling + Claude SDK)
- **Claude access:** Anthropic API (`anthropic` Python SDK), using a fast/cheap model for scoring since it's a high-volume, low-complexity task per listing
- **Storage:** SQLite for Phase 2+ (no server needed, one file)
- **Scheduling:** cron (Mac/Linux) or a simple `schedule` Python loop if running on a machine that's on
- **Digest output:** static HTML file styled with your portfolio's CSS variables, so it visually matches your personal brand — open it locally or host it the same way as your portfolio (Netlify)

---

## 7. First prompt to give Claude Code

> "Build me a Python script that fetches job listings from the France Travail API for marketing/growth marketing roles in Paris, sends each listing to the Claude API along with my profile criteria (in profile.md) to get a 1–10 fit score and one-line reasoning, and prints the results sorted by score, highest first. Start with just this — no database, no scheduling yet."

That single prompt gets you Phase 1. Once it works, iterate phase by phase rather than asking for everything at once — it'll produce cleaner code and you'll actually understand what each piece does.

---

## 8. Things to watch for

- **API keys**: France Travail and Adzuna both require free registration for API keys — do this first, it's a 10-minute step but blocks everything else
- **Rate limits**: don't fetch too aggressively; daily runs are more than enough
- **Scoring drift**: periodically sanity-check Claude's fit scores against your own judgment on a few listings, and refine the profile.md wording if it's consistently off
- **Don't scrape LinkedIn** — not just a ToS issue, but LinkedIn actively blocks and can flag your account
