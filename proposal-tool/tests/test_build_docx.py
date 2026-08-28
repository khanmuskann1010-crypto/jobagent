from pathlib import Path

from docx import Document

from src.build_docx import build_docx, safe_filename, unique_output_path


def test_safe_filename_strips_special_chars():
    assert safe_filename("Acme Corp, Inc.") == "Acme_Corp__Inc"


def test_safe_filename_never_empty():
    assert safe_filename("!!!") == "unnamed_company"


def test_unique_output_path_avoids_collision(tmp_path):
    first = unique_output_path(tmp_path, "Acme", "2026-08-28")
    first.touch()
    second = unique_output_path(tmp_path, "Acme", "2026-08-28")
    assert second != first
    assert second.name == "Acme_2026-08-28_2.docx"


def test_build_docx_smoke(tmp_path):
    out_path = tmp_path / "out.docx"
    proposal = {
        "situation_summary": "They need help hiring.",
        "recommended_services": [
            {
                "service_name": "RPO",
                "indicative_price": "EUR 4500/mo",
                "rationale": "They're hiring at volume.",
            }
        ],
        "next_step": "Book a call.",
        "gaps_to_confirm": ["Confirm headcount target"],
    }
    build_docx("Acme", proposal, out_path)

    assert out_path.exists()
    doc = Document(str(out_path))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Acme" in text
    assert "They need help hiring." in text
    assert "Book a call." in text
    assert "Confirm headcount target" in text


def test_build_docx_handles_empty_proposal(tmp_path):
    out_path = tmp_path / "out.docx"
    build_docx("Acme", {}, out_path)
    assert out_path.exists()
