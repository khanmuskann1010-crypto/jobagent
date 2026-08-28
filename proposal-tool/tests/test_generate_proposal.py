import anthropic
import pytest

from src.config import Config
from src.generate_proposal import (
    ProposalGenerationError,
    _extract_json,
    _normalize_proposal,
    generate_proposal,
    validate_catalog,
)

VALID_CATALOG = {
    "services": [
        {"service_id": "x", "service_name": "X", "base_price_eur": 100}
    ]
}
TEST_CONFIG = Config(
    anthropic_api_key="sk-test", model="claude-sonnet-5", request_timeout=5, max_retries=3
)


class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


def _make_api_error(cls, message, **extra_attrs):
    """
    Build an anthropic SDK exception instance without going through its real
    __init__ (which requires constructing an httpx Request/Response). Real
    httpx types aren't something we want this test suite depending on
    directly. args/message/status_code are all our code path actually reads.
    """
    err = Exception.__new__(cls)
    Exception.__init__(err, message)
    err.message = message
    for key, value in extra_attrs.items():
        setattr(err, key, value)
    return err


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


class _FakeAnthropicClient:
    def __init__(self, messages: _FakeMessages):
        self.messages = messages


def _patch_client(monkeypatch, side_effects):
    fake_messages = _FakeMessages(side_effects)
    fake_client = _FakeAnthropicClient(fake_messages)
    monkeypatch.setattr(
        "src.generate_proposal.anthropic.Anthropic", lambda **kwargs: fake_client
    )
    return fake_messages


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence():
    raw = '```json\n{"a": 1}\n```'
    assert _extract_json(raw) == {"a": 1}


def test_extract_json_strips_bare_fence():
    raw = '```\n{"a": 1}\n```'
    assert _extract_json(raw) == {"a": 1}


def test_normalize_proposal_fills_missing_keys():
    normalized = _normalize_proposal({"situation_summary": "hi"})
    assert normalized == {
        "situation_summary": "hi",
        "recommended_services": [],
        "next_step": "",
        "gaps_to_confirm": [],
    }


def test_normalize_proposal_handles_null_lists():
    normalized = _normalize_proposal(
        {"recommended_services": None, "gaps_to_confirm": None}
    )
    assert normalized["recommended_services"] == []
    assert normalized["gaps_to_confirm"] == []


def test_validate_catalog_rejects_empty_services():
    with pytest.raises(ProposalGenerationError):
        validate_catalog({"services": []})


def test_validate_catalog_rejects_missing_required_fields():
    with pytest.raises(ProposalGenerationError):
        validate_catalog({"services": [{"service_id": "x"}]})


def test_validate_catalog_accepts_well_formed_catalog():
    validate_catalog(
        {
            "services": [
                {
                    "service_id": "x",
                    "service_name": "X",
                    "base_price_eur": 100,
                }
            ]
        }
    )


def test_generate_proposal_succeeds_first_try(monkeypatch):
    _patch_client(
        monkeypatch,
        [_FakeResponse('{"situation_summary": "ok", "next_step": "call"}')],
    )
    result = generate_proposal({}, VALID_CATALOG, TEST_CONFIG)
    assert result["situation_summary"] == "ok"
    assert result["next_step"] == "call"


def test_generate_proposal_retries_transient_error_then_succeeds(monkeypatch):
    conn_error = _make_api_error(anthropic.APIConnectionError, "Connection error.")
    fake_messages = _patch_client(
        monkeypatch,
        [conn_error, _FakeResponse('{"situation_summary": "ok"}')],
    )
    monkeypatch.setattr("src.generate_proposal.time.sleep", lambda _: None)

    result = generate_proposal({}, VALID_CATALOG, TEST_CONFIG)
    assert result["situation_summary"] == "ok"
    assert fake_messages.calls == 2


def test_generate_proposal_raises_after_exhausting_retries(monkeypatch):
    conn_error = _make_api_error(anthropic.APIConnectionError, "Connection error.")
    _patch_client(monkeypatch, [conn_error, conn_error, conn_error])
    monkeypatch.setattr("src.generate_proposal.time.sleep", lambda _: None)

    with pytest.raises(ProposalGenerationError):
        generate_proposal({}, VALID_CATALOG, TEST_CONFIG)


def test_generate_proposal_auth_error_fails_immediately_without_retry(monkeypatch):
    auth_error = _make_api_error(
        anthropic.AuthenticationError, "bad key", status_code=401, body=None
    )
    fake_messages = _patch_client(monkeypatch, [auth_error])

    with pytest.raises(ProposalGenerationError, match="API key"):
        generate_proposal({}, VALID_CATALOG, TEST_CONFIG)
    assert fake_messages.calls == 1


def test_generate_proposal_invalid_json_fails_soft_without_retry(monkeypatch):
    fake_messages = _patch_client(monkeypatch, [_FakeResponse("not json at all")])
    result = generate_proposal({}, VALID_CATALOG, TEST_CONFIG)
    assert "raw_output" in result
    assert result["raw_output"] == "not json at all"
    assert fake_messages.calls == 1


def test_generate_proposal_rejects_invalid_catalog_before_any_api_call(monkeypatch):
    fake_messages = _patch_client(monkeypatch, [])
    with pytest.raises(ProposalGenerationError):
        generate_proposal({}, {"services": []}, TEST_CONFIG)
    assert fake_messages.calls == 0
