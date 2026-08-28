"""
Central config loading + validation.

Fails fast with a clear message if required settings are missing, instead
of letting a cryptic error surface halfway through a run (e.g. deep inside
the anthropic SDK).
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-5"
CATALOG_PATH = Path(__file__).parent.parent / "service_catalog.json"


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    model: str
    request_timeout: int
    max_retries: int


def load_config() -> Config:
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in, "
            "or export ANTHROPIC_API_KEY in your shell before running."
        )

    model = os.environ.get("PROPOSAL_TOOL_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    try:
        timeout = int(os.environ.get("PROPOSAL_TOOL_TIMEOUT", "30"))
    except ValueError as exc:
        raise ConfigError("PROPOSAL_TOOL_TIMEOUT must be an integer (seconds).") from exc

    try:
        retries = int(os.environ.get("PROPOSAL_TOOL_MAX_RETRIES", "3"))
    except ValueError as exc:
        raise ConfigError("PROPOSAL_TOOL_MAX_RETRIES must be an integer.") from exc

    return Config(
        anthropic_api_key=api_key,
        model=model,
        request_timeout=timeout,
        max_retries=retries,
    )
