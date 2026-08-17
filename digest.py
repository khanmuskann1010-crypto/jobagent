"""
Generates a static HTML digest of scored listings, styled in an
emerald/gold palette. Self-contained (inline CSS, no external assets) so
it can be opened locally or hosted as-is (e.g. on Netlify).
"""

from datetime import datetime
from pathlib import Path

TIER_STYLES = {
    "strong": ("Strong fit", "#0f6b4c", "#e7f5ee"),
    "worth-a-look": ("Worth a look", "#8a6d1a", "#faf3dd"),
    "low": ("Low fit", "#666666", "#f0f0f0"),
}


def _tier(score: int) -> str:
    if score >= 8:
        return "strong"
    if score >= 5:
        return "worth-a-look"
    return "low"


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _card(job: dict, index: int) -> str:
    label, fg, bg = TIER_STYLES[_tier(job["score"])]
    url = job.get("url") or "#"
    contract = f" · {_escape(job['contract_type'])}" if job.get("contract_type") else ""
    return f"""
    <article class="card">
      <div class="card-top">
        <span class="badge" style="color:{fg};background:{bg};">#{index} · {job['score']}/10 · {label}</span>
        <span class="source">{_escape(job['source']).replace('_', ' ').title()}</span>
      </div>
      <h2><a href="{url}" target="_blank" rel="noopener">{_escape(job['title'])}</a></h2>
      <p class="meta">{_escape(job['company'])} — {_escape(job['location'])}{contract}</p>
      <p class="reason">{_escape(job['reason'])}</p>
    </article>"""


def generate_html(scored_listings: list[dict], output_path: Path) -> Path:
    date_str = datetime.now().strftime("%A, %B %d %Y")
    count = len(scored_listings)
    cards = "\n".join(_card(j, i) for i, j in enumerate(scored_listings, start=1)) or (
        '<p class="empty">No new listings met the bar today.</p>'
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job Digest — {date_str}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --emerald: #0f6b4c;
    --emerald-dark: #0a4a34;
    --gold: #c9a227;
    --bg: #faf9f6;
    --card-bg: #ffffff;
    --text: #1f2a26;
    --muted: #5b6b64;
    --border: #e4e1d8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    padding: 2.5rem 1.5rem 4rem;
  }}
  .wrap {{ max-width: 780px; margin: 0 auto; }}
  header {{
    border-bottom: 3px solid var(--gold);
    padding-bottom: 1.25rem;
    margin-bottom: 2rem;
  }}
  header h1 {{
    margin: 0 0 0.25rem;
    color: var(--emerald-dark);
    font-size: 1.75rem;
  }}
  header p {{ margin: 0; color: var(--muted); }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-left: 4px solid var(--emerald);
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
  }}
  .card-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }}
  .badge {{
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
  }}
  .source {{
    font-size: 0.75rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .card h2 {{ margin: 0 0 0.35rem; font-size: 1.15rem; }}
  .card h2 a {{ color: var(--emerald-dark); text-decoration: none; }}
  .card h2 a:hover {{ text-decoration: underline; }}
  .meta {{ margin: 0 0 0.5rem; color: var(--muted); font-size: 0.9rem; }}
  .reason {{ margin: 0; font-size: 0.95rem; }}
  .empty {{ color: var(--muted); text-align: center; padding: 3rem 0; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Job Digest</h1>
      <p>{date_str} · {count} new listing{'s' if count != 1 else ''} scored</p>
    </header>
    {cards}
  </div>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
