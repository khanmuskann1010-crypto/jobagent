import pytest

from src.config import ConfigError, load_config


def _clear_env(monkeypatch):
    for var in (
        "ANTHROPIC_API_KEY",
        "FRANCE_TRAVAIL_CLIENT_ID",
        "FRANCE_TRAVAIL_CLIENT_SECRET",
        "JOB_AGENT_MODEL",
        "JOB_AGENT_TIMEOUT",
        "JOB_AGENT_MAX_RETRIES",
    ):
        monkeypatch.delenv(var, raising=False)


def test_load_config_raises_when_all_missing(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_config()


def test_load_config_lists_all_missing_vars(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "FRANCE_TRAVAIL_CLIENT_ID" in str(exc_info.value)
    assert "FRANCE_TRAVAIL_CLIENT_SECRET" in str(exc_info.value)
    assert "ANTHROPIC_API_KEY" not in str(exc_info.value)


def test_load_config_uses_defaults(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_ID", "id")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_SECRET", "secret")
    monkeypatch.chdir(tmp_path)

    config = load_config()
    assert config.model == "claude-sonnet-5"
    assert config.request_timeout == 15
    assert config.max_retries == 3


def test_load_config_rejects_non_integer_timeout(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_ID", "id")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("JOB_AGENT_TIMEOUT", "soon")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError):
        load_config()
