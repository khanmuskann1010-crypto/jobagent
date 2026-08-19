"""
Seeds jobs.db with fictional listings for the public Dextor demo (see the
'demo' branch) - no real companies, no real application history. Spans every
status/feature so the dashboard looks fully populated: a scheduled
interview, a rejection, a skipped low-score listing, a dead link, and a
cross-source duplicate pair (to show off dedupe.py's "Also on ..." note).

Run once when (re)building the demo branch's jobs.db:
    python seed_demo_data.py
"""

from datetime import datetime, timedelta, timezone

import db

DB_PATH = db.DB_PATH


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


LISTINGS = [
    # (source, id, title, company, location, contract, url, posted, score, reason, salary, seen_days_ago, status, status_days_ago, interview_in_days, link_status)
    ("indeed", "DEMO1", "Growth & Lifecycle Marketing Manager", "Palisade Fintech", "Paris (75)", "CDI",
     "https://example.com/demo/palisade-growth", "Aug 2026", 9,
     "Near-exact match: growth + lifecycle ownership at a Series B fintech, hands-on execution with strategic scope.",
     "€44 000–50 000", 12, "new", None, None, "live"),

    ("adzuna", "DEMO2", "Marketing Communications Coordinator", "Verdant Health", "Paris (75)", "CDI",
     "https://example.com/demo/verdant-comms", "Aug 2026", 8,
     "Strong overlap with multi-brand comms coordination experience; healthtech is adjacent to current EdTech/SaaS background.",
     "€38 000–42 000", 10, "applied", 6, None, "live"),

    ("france_travail", "DEMO3", "Digital Marketing Executive", "Northwind Logistics", "Levallois-Perret (92)", "CDI",
     "https://example.com/demo/northwind-digital", "Jul 2026", 7,
     "Good growth-leaning digital marketing scope; logistics is a new vertical but transferable skills apply.",
     "", 9, "interviewing", 3, 6, "live"),

    ("indeed", "DEMO4", "Growth Marketing Specialist", "Kindle Learning", "Paris (75)", "CDI",
     "https://example.com/demo/kindle-growth-1", "Aug 2026", 8,
     "Direct EdTech growth marketing match, same sector as prior B2C growth experience at scale.",
     "€40 000", 5, "new", None, None, "unknown"),

    ("wttj", "DEMO4B", "Growth Marketing Specialist H/F", "Kindle Learning", "Paris (75)", "CDI",
     "https://example.com/demo/kindle-growth-2", "Aug 2026", 7,
     "Same posting as the Indeed listing above, likely cross-posted.",
     "€40 000", 5, "new", None, None, "unknown"),

    ("adzuna", "DEMO5", "Marketing Operations Manager", "Bristlecone Robotics", "Boulogne-Billancourt (92)", "CDI",
     "https://example.com/demo/bristlecone-ops", "Jul 2026", 6,
     "AI-assisted content/SEO ops overlap is strong, though the robotics industry is unfamiliar territory.",
     "", 8, "new", None, None, "live"),

    ("indeed", "DEMO6", "Content & SEO Lead", "Solstice Media", "Paris (75)", "CDI",
     "https://example.com/demo/solstice-seo", "Jun 2026", 5,
     "Reasonable SEO/content overlap but skews more purely creative than growth-oriented.",
     "", 20, "rejected", 4, None, "dead"),

    ("france_travail", "DEMO7", "Junior Marketing Assistant", "Anchor Retail", "Paris (75)", "CDI",
     "", "Jun 2026", 2,
     "Entry-level title - below target seniority per profile.md.",
     "", 18, "skipped", 18, None, "unknown"),

    ("adzuna", "DEMO8", "Business Development Representative", "Ferrous Metals Co", "Paris (75)", "CDI",
     "https://example.com/demo/ferrous-bdr", "Aug 2026", 1,
     "Pure sales role - explicit deal-breaker per profile.md.",
     "", 3, "new", None, None, "unknown"),

    ("indeed", "DEMO9", "Growth Marketing Executive", "Halcyon Beauty", "Paris (75)", "CDI",
     "https://example.com/demo/halcyon-growth", "Aug 2026", 8,
     "Strong growth marketing scope with campaign ownership; consumer beauty is a new but plausible vertical.",
     "€41 000–46 000", 2, "new", None, None, "live"),
]


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()  # start clean, this is demo-only data

    scored = [
        {
            "source": s, "id": jid, "title": title, "company": company, "location": location,
            "description": f"(demo listing) {title} at {company}.", "contract_type": contract,
            "url": url, "date_posted": posted, "score": score, "reason": reason, "salary": salary,
        }
        for (s, jid, title, company, location, contract, url, posted, score, reason, salary,
             seen_days, status, status_days, interview_in, link_status) in LISTINGS
    ]
    db.save_scored(scored)

    with db.connect() as conn:
        for (s, jid, title, company, location, contract, url, posted, score, reason, salary,
             seen_days, status, status_days, interview_in, link_status) in LISTINGS:
            conn.execute(
                "UPDATE seen_jobs SET first_seen_at = ?, link_status = ?, link_checked_at = ? WHERE source = ? AND external_id = ?",
                (days_ago(seen_days), link_status, days_ago(0), s, jid),
            )
            if status != "new":
                changed_at = days_ago(status_days)
                conn.execute(
                    "UPDATE seen_jobs SET status = ?, status_updated_at = ? WHERE source = ? AND external_id = ?",
                    (status, changed_at, s, jid),
                )
                conn.execute(
                    "INSERT INTO status_history (source, external_id, status, changed_at) VALUES (?, ?, ?, ?)",
                    (s, jid, status, changed_at),
                )
            if interview_in is not None:
                when = (datetime.now(timezone.utc) + timedelta(days=interview_in)).isoformat()
                conn.execute(
                    "UPDATE seen_jobs SET interview_at = ? WHERE source = ? AND external_id = ?",
                    (when, s, jid),
                )

    print(f"Seeded {len(LISTINGS)} demo listings into {DB_PATH}")


if __name__ == "__main__":
    main()
