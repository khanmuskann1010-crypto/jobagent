import anthropic
import pytest

from src.config import Config
from src.score_jobs import ScoreJobsError, _extract_json, score_all, score_listing

TEST_CONFIG = Config(
    anthropic_api_key="sk-test",
    france_travail_client_id="id",
    france_travail_client_secret="secret",
    model="claude-sonnet-5",
    request_timeout=5,
    max_retries=3,
)

SAMPLE_LISTING = {
    "id": "1",
    "title": "Growth Marketing Manager",
    "company": "Acme",
    "location": "Paris",
    "contract_type": "CDI",
    "description": "Own our growth marketing strategy.",
    "url": "https://example.test/job/1",
    "date_posted": "2026-08-01",
}


def _make_api_error(cls, message, **extra_attrs):
    err = Exception.__new__(cls)
    Exception.__init__(err, message)
    err.message = message
    for key, value in extra_attrs.items():
        setattr(err, key, value)
    return err


class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakeClient:
    def __init__(self, messages):
        self.messages = messages


def test_extract_json_plain():
    assert _extract_json('{"score": 7, "reason": "good fit"}') == {"score": 7, "reason": "good fit"}


def test_extract_json_strips_fence():
    assert _extract_json('```json\n{"score": 5, "reason": "ok"}\n```') == {"score": 5, "reason": "ok"}


def test_score_listing_succeeds(monkeypatch):
    messages = _FakeMessages([_FakeResponse('{"score": 8, "reason": "strong match"}')])
    client = _FakeClient(messages)
    result = score_listing(client, "profile text", SAMPLE_LISTING, TEST_CONFIG)
    assert result == {"score": 8, "reason": "strong match"}


def test_score_listing_handles_malformed_json_without_retry(monkeypatch):
    messages = _FakeMessages([_FakeResponse("not json")])
    client = _FakeClient(messages)
    result = score_listing(client, "profile text", SAMPLE_LISTING, TEST_CONFIG)
    assert result["score"] == 0
    assert "Could not parse" in result["reason"]
    assert messages.calls == 1


def test_score_listing_retries_transient_error_then_succeeds(monkeypatch):
    conn_error = _make_api_error(anthropic.APIConnectionError, "Connection error.")
    messages = _FakeMessages([conn_error, _FakeResponse('{"score": 6, "reason": "ok"}')])
    client = _FakeClient(messages)
    monkeypatch.setattr("src.score_jobs.time.sleep", lambda _: None)

    result = score_listing(client, "profile text", SAMPLE_LISTING, TEST_CONFIG)
    assert result == {"score": 6, "reason": "ok"}
    assert messages.calls == 2


def test_score_listing_returns_zero_after_exhausting_retries(monkeypatch):
    conn_error = _make_api_error(anthropic.APIConnectionError, "Connection error.")
    messages = _FakeMessages([conn_error, conn_error, conn_error])
    client = _FakeClient(messages)
    monkeypatch.setattr("src.score_jobs.time.sleep", lambda _: None)

    result = score_listing(client, "profile text", SAMPLE_LISTING, TEST_CONFIG)
    assert result["score"] == 0
    assert "failed after retries" in result["reason"]


def test_score_listing_raises_on_auth_error_without_retry(monkeypatch):
    auth_error = _make_api_error(anthropic.AuthenticationError, "bad key", status_code=401, body=None)
    messages = _FakeMessages([auth_error])
    client = _FakeClient(messages)

    with pytest.raises(ScoreJobsError, match="API key"):
        score_listing(client, "profile text", SAMPLE_LISTING, TEST_CONFIG)
    assert messages.calls == 1


def test_score_all_returns_empty_list_for_no_listings():
    assert score_all([], TEST_CONFIG) == []


def test_score_all_sorts_highest_first(monkeypatch, tmp_path):
    profile_path = tmp_path / "profile.md"
    profile_path.write_text("Target roles: growth marketing")
    monkeypatch.setattr("src.score_jobs.PROFILE_PATH", profile_path)

    messages = _FakeMessages(
        [
            _FakeResponse('{"score": 3, "reason": "weak"}'),
            _FakeResponse('{"score": 9, "reason": "great"}'),
        ]
    )
    monkeypatch.setattr(
        "src.score_jobs.anthropic.Anthropic", lambda **kwargs: _FakeClient(messages)
    )

    listings = [SAMPLE_LISTING, {**SAMPLE_LISTING, "id": "2", "title": "Other Role"}]
    scored = score_all(listings, TEST_CONFIG)

    assert [s["score"] for s in scored] == [9, 3]
