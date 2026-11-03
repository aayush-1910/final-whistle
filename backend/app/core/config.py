"""
Final Whistle — Application configuration.

Loads environment variables at startup and validates that required
secrets are present.  Fails fast with a clear message if anything
is missing so that the app never runs with placeholder credentials.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Locate the .env file — the root .env is the source of truth.
# backend/.env (if present) only fills in variables the root file lacks;
# load_dotenv never overrides an already-set variable, so root wins.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
_ROOT_DIR = _BACKEND_DIR.parent  # final-whistle/

for _env_file in (_ROOT_DIR / ".env", _BACKEND_DIR / ".env"):
    if _env_file.is_file():
        load_dotenv(_env_file)


def _require(name: str) -> str:
    """Return an env-var value or abort with a helpful message."""
    value = os.getenv(name)
    if not value or value == "replace_me":
        print(
            f"\n[FATAL] Environment variable '{name}' is missing or still "
            f"set to 'replace_me'.\n"
            f"  → Copy .env.example to .env and fill in your real credentials.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _optional(name: str, default: str = "") -> str:
    """Return an env-var value or a default (empty string)."""
    value = os.getenv(name, default)
    return default if value == "replace_me" else value


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded once at import time."""

    # Football data provider
    api_football_key: str = field(default_factory=lambda: _require("API_FOOTBALL_KEY"))
    api_football_base_url: str = "https://v3.football.api-sports.io"

    # football-data.org (separate service, separate token — see OD-001)
    football_data_org_key: str = field(default_factory=lambda: _optional("FOOTBALL_DATA_ORG_KEY"))

    # Supabase
    supabase_url: str = field(default_factory=lambda: _require("SUPABASE_URL"))
    supabase_service_role_key: str = field(
        default_factory=lambda: _require("SUPABASE_SERVICE_ROLE_KEY")
    )
    supabase_anon_key: str = field(default_factory=lambda: _optional("SUPABASE_ANON_KEY"))

    # Application
    app_env: str = field(default_factory=lambda: _optional("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: _optional("LOG_LEVEL", "INFO"))

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


# Singleton — import this from other modules.
settings = Settings()
