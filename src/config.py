"""
Central config loading + validation.

Fails fast with a clear message if required settings are missing, instead
of letting a cryptic error surface halfway through a run.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    france_travail_client_id: str
    france_travail_client_secret: str
    model: str
    request_timeout: int
    max_retries: int


def load_config() -> Config:
    load_dotenv()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    ft_id = os.environ.get("FRANCE_TRAVAIL_CLIENT_ID", "").strip()
    ft_secret = os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET", "").strip()

    missing = []
    if not anthropic_key:
        missing.append("ANTHROPIC_API_KEY")
    if not ft_id:
        missing.append("FRANCE_TRAVAIL_CLIENT_ID")
    if not ft_secret:
        missing.append("FRANCE_TRAVAIL_CLIENT_SECRET")

    if missing:
        raise ConfigError(
            f"Missing required config: {', '.join(missing)}. "
            "Copy .env.example to .env and fill it in, or export these in your shell."
        )

    model = os.environ.get("JOB_AGENT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        timeout = int(os.environ.get("JOB_AGENT_TIMEOUT", "15"))
    except ValueError as exc:
        raise ConfigError("JOB_AGENT_TIMEOUT must be an integer (seconds).") from exc

    try:
        retries = int(os.environ.get("JOB_AGENT_MAX_RETRIES", "3"))
    except ValueError as exc:
        raise ConfigError("JOB_AGENT_MAX_RETRIES must be an integer.") from exc

    return Config(
        anthropic_api_key=anthropic_key,
        france_travail_client_id=ft_id,
        france_travail_client_secret=ft_secret,
        model=model,
        request_timeout=timeout,
        max_retries=retries,
    )
