import pytest

from src.config import ConfigError, load_config


def test_load_config_raises_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here to be picked up
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("PROPOSAL_TOOL_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.anthropic_api_key == "sk-test"
    assert config.model == "claude-sonnet-5"
    assert config.request_timeout == 30
    assert config.max_retries == 3


def test_load_config_rejects_non_integer_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PROPOSAL_TOOL_TIMEOUT", "not-a-number")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_config()
