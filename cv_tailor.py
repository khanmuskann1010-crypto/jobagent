"""
Uses Groq's free API (openai/gpt-oss-120b) to tailor CV suggestions to one
specific job listing: which requirements matter most, how your existing
experience maps to them, and concrete bullet/opening-line rewrites to use
when you apply.
"""

import json
from pathlib import Path

from groq import Groq

CV_PATH = Path(__file__).parent / "cv.md"
OUTPUT_DIR = Path(__file__).parent / "cv_suggestions"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are a resume coach helping one specific candidate tailor \
their CV to a single job listing. You will be given the candidate's CV and a \
job listing. Respond with ONLY a JSON object, no other text, no markdown fences:

{
  "top_requirements": ["<requirement 1>", "<requirement 2>", ...],
  "matches": [{"requirement": "...", "evidence": "<specific CV evidence, or 'No direct match - consider framing X as a transferable skill'>"}],
  "bullet_suggestions": ["<rewritten/new CV bullet tailored to this job>", ...],
  "opening_line": "<one or two sentence tailored opener for a cover letter or outreach note>"
}

top_requirements: up to 5, most important first.
bullet_suggestions: 2-4 bullets.

Be concrete and specific - reference actual companies/skills from the CV, and \
actual requirements from the listing. Do not invent experience that isn't in \
the CV."""


def load_cv() -> str:
    if not CV_PATH.exists():
        raise FileNotFoundError(
            f"{CV_PATH} not found - fill in cv.md with your CV content first."
        )
    return CV_PATH.read_text()


def tailor_for_job(client: Groq, cv_text: str, job: dict) -> dict:
    user_content = f"""CANDIDATE CV:
{cv_text}

JOB LISTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {job['description'][:3000]}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1536,
            reasoning_effort="low",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as e:
        return {"error": f"Tailoring request failed: {e}"}

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"error": f"Could not parse model response: {raw_text[:200]}"}


def save_suggestions(job: dict, suggestions: dict, index: int) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_company = "".join(c if c.isalnum() else "_" for c in job["company"])
    path = OUTPUT_DIR / f"job_{index}_{safe_company}.md"

    lines = [f"# Tailored CV notes — {job['title']} @ {job['company']}\n"]
    if "error" in suggestions:
        lines.append(suggestions["error"])
    else:
        lines.append("## Top requirements\n")
        lines += [f"- {r}" for r in suggestions.get("top_requirements", [])]
        lines.append("\n## How your CV matches\n")
        for m in suggestions.get("matches", []):
            lines.append(f"- **{m['requirement']}**: {m['evidence']}")
        lines.append("\n## Suggested CV bullets\n")
        lines += [f"- {b}" for b in suggestions.get("bullet_suggestions", [])]
        lines.append(f"\n## Suggested opening line\n\n{suggestions.get('opening_line', '')}")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
