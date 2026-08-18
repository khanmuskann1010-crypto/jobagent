"""
Uses Groq's free API (openai/gpt-oss-120b) to draft a tailored cover letter
for one specific job listing, grounded in the candidate's real CV - same
honesty rules as cv_tailor.py: it can only reference experience that's
actually in the CV, never invent anything - rendered as a one-page PDF.
"""

import json
from pathlib import Path

from fpdf import FPDF, XPos, YPos
from groq import Groq

import groq_usage
from cv_tailor import OUTPUT_DIR, _pdf_safe
from groq_errors import friendly_groq_error

CV_PATH = Path(__file__).parent / "cv.md"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are an expert cover letter writer producing one tailored cover letter \
for one candidate applying to one specific job. You will be given the candidate's real CV and a \
job listing. Respond with ONLY a JSON object, no other text, no markdown fences, in the SAME \
LANGUAGE as the original CV:

{
  "name": "<candidate's full name, copied EXACTLY from the CV>",
  "contact": "<contact line - phone, email, location, links - copied EXACTLY from the CV>",
  "date": "<today's date, human-readable, in the CV's language>",
  "salutation": "<e.g. 'Dear Hiring Manager,' or 'Madame, Monsieur,' matching the CV's language>",
  "paragraphs": ["<opening paragraph - the role and why this candidate>", "<body paragraph(s) - \
specific real experience from the CV that fits this job>", "<closing paragraph - enthusiasm and \
call to action>"],
  "sign_off": "<e.g. 'Sincerely,' or 'Cordialement,' matching the CV's language>"
}

CRITICAL RULES - breaking any of these makes the letter unusable and dishonest:
- Never invent a company, job title, achievement, or metric not already in the original CV.
- Every claim about the candidate's experience must trace back to something actually in the CV - \
you may select, emphasize, and rephrase, never add.
- 3-4 paragraphs total, each 2-4 sentences. This is a one-page letter, not an essay.
- Address the specific job and company by name where natural."""


def load_cv() -> str:
    if not CV_PATH.exists():
        raise FileNotFoundError(f"{CV_PATH} not found - fill in cv.md with your CV content first.")
    return CV_PATH.read_text()


def generate_cover_letter(client: Groq, cv_text: str, job: dict, attempts: int = 2) -> dict:
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
                max_tokens=2000,
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
            groq_usage.record_limit_hit(e)
            last_error = friendly_groq_error(e)
            continue

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            last_error = f"Could not parse model response: {raw_text[:200]}"
            continue

    return {"error": last_error}


def save_cover_letter(job: dict, letter: dict) -> Path:
    """Writes a PDF keyed on the listing's own (source, id), same convention as cv_tailor.py."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe_company = "".join(c if c.isalnum() else "_" for c in job["company"])
    safe_id = "".join(c if c.isalnum() else "_" for c in str(job.get("id", "unknown")))
    path = OUTPUT_DIR / f"{job.get('source', 'job')}_{safe_id}_{safe_company}_CoverLetter.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def name_line(text: str) -> None:
        pdf.set_font("Helvetica", "B", 16)
        pdf.multi_cell(0, 8, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def muted(text: str, size: int = 10) -> None:
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 6, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    def body(text: str) -> None:
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, _pdf_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if "error" in letter:
        name_line("Something went wrong")
        body(letter["error"])
        pdf.output(str(path))
        return path

    name_line(letter.get("name", "") or job["title"])
    if letter.get("contact"):
        muted(letter["contact"], size=9)
    if letter.get("date"):
        muted(letter["date"], size=9)
    pdf.ln(6)

    if letter.get("salutation"):
        body(letter["salutation"])
        pdf.ln(3)

    for para in letter.get("paragraphs", []):
        body(para)
        pdf.ln(3)

    if letter.get("sign_off"):
        body(letter["sign_off"])
        pdf.ln(2)
        body(letter.get("name", ""))

    pdf.output(str(path))
    return path
