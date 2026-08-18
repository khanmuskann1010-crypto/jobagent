"""
Uses Groq's free API (openai/gpt-oss-120b) to tailor CV suggestions to one
specific job listing: which requirements matter most, how your existing
experience maps to them, and concrete bullet/opening-line rewrites to use
when you apply.
"""

import json
from pathlib import Path

from fpdf import FPDF, XPos, YPos
from groq import Groq

CV_PATH = Path(__file__).parent / "cv.md"
OUTPUT_DIR = Path(__file__).parent / "cv_suggestions"
MODEL = "openai/gpt-oss-120b"

# FPDF's built-in fonts only support Windows ANSI (cp1252) - covers all
# standard French/English accented letters, but not smart quotes, em-dashes,
# or emoji that an LLM might emit. Normalize the common ones and let
# anything else degrade to '?' rather than crash the whole request.
_PDF_CHAR_REPLACEMENTS = {
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "–": "-", "—": "-",
    "…": "...",
    "•": "-",
}


def _pdf_safe(text: str) -> str:
    if not text:
        return ""
    for orig, repl in _PDF_CHAR_REPLACEMENTS.items():
        text = text.replace(orig, repl)
    return text.encode("latin-1", errors="replace").decode("latin-1")

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
    description = (job.get("description") or "")[:3000]
    user_content = f"""CANDIDATE CV:
{cv_text}

JOB LISTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {description}"""

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


def save_suggestions(job: dict, suggestions: dict) -> Path:
    """Writes a PDF keyed on the listing's own (source, id) - unique per
    listing, unlike a caller-supplied index which can collide across
    different listings at the same company."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_company = "".join(c if c.isalnum() else "_" for c in job["company"])
    safe_id = "".join(c if c.isalnum() else "_" for c in str(job.get("id", "unknown")))
    path = OUTPUT_DIR / f"{job.get('source', 'job')}_{safe_id}_{safe_company}.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def heading(text: str) -> None:
        pdf.set_font("Helvetica", "B", 18)
        pdf.multi_cell(0, 9, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def subheading(text: str) -> None:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(15, 107, 76)  # emerald, matches the rest of the app
        pdf.multi_cell(0, 8, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(0, 6, _pdf_safe(f"- {text}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    heading(f"{job['title']}")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 7, _pdf_safe(f"{job['company']} - {job.get('location', '')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    if "error" in suggestions:
        subheading("Something went wrong")
        body(suggestions["error"])
    else:
        subheading("Top requirements")
        for r in suggestions.get("top_requirements", []):
            bullet(r)

        subheading("How your CV matches")
        for m in suggestions.get("matches", []):
            bullet(f"{m['requirement']}: {m['evidence']}")

        subheading("Suggested CV bullets")
        for b in suggestions.get("bullet_suggestions", []):
            bullet(b)

        subheading("Suggested opening line")
        body(suggestions.get("opening_line", ""))

    pdf.output(str(path))
    return path
