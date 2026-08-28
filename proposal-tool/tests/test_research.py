import requests

from src.research import _validate_url, research_company


def test_validate_url_rejects_non_http_schemes():
    assert _validate_url("file:///etc/passwd") is not None
    assert _validate_url("ftp://example.com") is not None


def test_validate_url_rejects_missing_host():
    assert _validate_url("http://") is not None


def test_validate_url_accepts_https():
    assert _validate_url("https://example.com") is None


def test_research_company_no_url_returns_notes_only():
    result = research_company("Acme", "", "hiring 5 engineers")
    assert result["name"] == "Acme"
    assert result["user_notes"] == "hiring 5 engineers"
    assert result["homepage_text"] == ""
    assert result["fetch_error"] is None


def test_research_company_bad_scheme_sets_fetch_error_without_network_call():
    result = research_company("Acme", "javascript:alert(1)", "")
    assert result["fetch_error"] is not None
    assert result["homepage_text"] == ""


def test_research_company_handles_connection_error(monkeypatch):
    def raise_conn_error(*args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("src.research.requests.get", raise_conn_error)
    result = research_company("Acme", "https://example.invalid", "")
    assert result["fetch_error"] == "boom"
    assert result["homepage_text"] == ""
