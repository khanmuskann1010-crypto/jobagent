"""
Uses Groq's free API (openai/gpt-oss-120b) to produce a tailored version of
your actual CV for one specific job listing - same roles, companies, and
dates, with the summary/skills/bullets re-emphasized and reworded for that
job - rendered as a one-page PDF you can actually submit.
"""

import json
from pathlib import Path

from fpdf import FPDF, XPos, YPos
from groq import Groq

import groq_usage
from groq_errors import friendly_groq_error

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

SYSTEM_PROMPT = """You are an expert resume writer producing a tailored version \
of one candidate's real CV for one specific job listing. You will be given the \
candidate's full CV and a job listing. Respond with ONLY a JSON object, no other \
text, no markdown fences, in the SAME LANGUAGE as the original CV:

{
  "name": "<candidate's full name, copied EXACTLY from the CV>",
  "contact": "<contact line - phone, email, location, links - copied EXACTLY from the CV>",
  "headline": "<a professional headline for this specific role, in the candidate's own style>",
  "summary": "<3-4 sentence professional summary, tailored to emphasize fit for THIS job>",
  "skills": ["<skill>", ...],  // at most 10, the most relevant to this job
  "experience": [
    {
      "title": "<EXACT role title from the CV, unchanged>",
      "company": "<EXACT company name from the CV, unchanged>",
      "dates": "<EXACT dates from the CV, unchanged>",
      "location": "<EXACT location from the CV, unchanged, or empty string>",
      "bullets": ["<bullet re-emphasized/reworded for this job>", ...]
    }
  ],
  "education": "<education section, copied from the CV>",
  "certifications_languages": "<certifications and languages, copied from the CV>"
}

CRITICAL RULES - breaking any of these makes the output unusable and dishonest:
- Never invent a company, job title, date, degree, or certification that isn't \
in the original CV.
- Never invent a metric or achievement not already present in the original CV - \
you may rephrase and re-emphasize what's already there, never add new claims.
- Company names, job titles, and dates inside "experience" must be copied \
EXACTLY as they appear in the original CV, character for character.
- Every role in the original CV must appear in "experience", in the same order \
- do not drop or merge any.
- "skills" must only contain skills that already appear in the original CV, \
capped at 10, chosen for relevance to this job - not a copy of every skill listed.
- Keep bullets per role to 2-4, and each bullet to one sentence. Be concise - \
this is a one-page CV, not an essay."""


def load_cv() -> str:
    if not CV_PATH.exists():
        raise FileNotFoundError(
            f"{CV_PATH} not found - fill in cv.md with your CV content first."
        )
    return CV_PATH.read_text()


def tailor_for_job(client: Groq, cv_text: str, job: dict, attempts: int = 2) -> dict:
    # Groq's free tier caps openai/gpt-oss-120b at 8000 tokens/minute total,
    # counting input + reserved max_tokens together in a single request -
    # confirmed via a live 413 (Requested 9972 against Limit 8000) with the
    # earlier max_tokens=8000. Keep the job description short so input stays
    # small, and cap max_tokens well under the remaining headroom.
    description = (job.get("description") or "")[:1500]
    user_content = f"""CANDIDATE CV:
{cv_text}

JOB LISTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {description}"""

    last_error = "unknown error"
    for _ in range(attempts):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=4500,
                reasoning_effort="low",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            raw_text = response.choices[0].message.content.strip()
            groq_usage.record_usage(response)
        except Exception as e:
            # A full CV response is long enough that the model occasionally
            # runs out of budget mid-JSON (even with generous max_tokens) and
            # Groq rejects the incomplete output outright - worth one retry
            # before giving up, since it's an independent roll of the dice.
            groq_usage.record_limit_hit(e)
            last_error = friendly_groq_error(e)
            continue

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            last_error = f"Could not parse model response: {raw_text[:200]}"
            continue

    return {"error": last_error}


def save_tailored_cv(job: dict, cv_data: dict) -> Path:
    """Writes a PDF keyed on the listing's own (source, id) - unique per
    listing, unlike a caller-supplied index which can collide across
    different listings at the same company."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_company = "".join(c if c.isalnum() else "_" for c in job["company"])
    safe_id = "".join(c if c.isalnum() else "_" for c in str(job.get("id", "unknown")))
    path = OUTPUT_DIR / f"{job.get('source', 'job')}_{safe_id}_{safe_company}_CV.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def name_line(text: str) -> None:
        pdf.set_font("Helvetica", "B", 20)
        pdf.multi_cell(0, 10, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def muted(text: str, size: int = 10) -> None:
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 6, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    def section(text: str) -> None:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(15, 107, 76)  # emerald, matches the rest of the app
        pdf.multi_cell(0, 8, _pdf_safe(text.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(15, 107, 76)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(2)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(pdf.l_margin + 4)
        pdf.multi_cell(0, 6, _pdf_safe(f"- {text}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if "error" in cv_data:
        name_line("Something went wrong")
        body(cv_data["error"])
        pdf.output(str(path))
        return path

    name_line(cv_data.get("name", "") or job["title"])
    if cv_data.get("headline"):
        muted(cv_data["headline"], size=12)
    if cv_data.get("contact"):
        muted(cv_data["contact"], size=9)

    if cv_data.get("summary"):
        section("Summary")
        body(cv_data["summary"])

    if cv_data.get("skills"):
        section("Skills")
        body(" | ".join(cv_data["skills"]))

    if cv_data.get("experience"):
        section("Experience")
        for role in cv_data["experience"]:
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(
                0, 7, _pdf_safe(f"{role.get('title', '')} - {role.get('company', '')}"),
                new_x=XPos.LMARGIN, new_y=YPos.NEXT,
            )
            meta = " | ".join(x for x in [role.get("dates", ""), role.get("location", "")] if x)
            if meta:
                muted(meta, size=9)
            for b in role.get("bullets", []):
                bullet(b)
            pdf.ln(2)

    if cv_data.get("education"):
        section("Education")
        body(cv_data["education"])

    if cv_data.get("certifications_languages"):
        section("Certifications & Languages")
        body(cv_data["certifications_languages"])

    pdf.output(str(path))
    return path
