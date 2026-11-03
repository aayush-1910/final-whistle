"""
Postgres connection for the backend.

Uses DATABASE_URL if set; otherwise derives the Supabase direct-connection
host (db.<project-ref>.supabase.co) from SUPABASE_URL and authenticates with
SUPABASE_DB_PASSWORD.  The password is passed as a separate parameter and is
never logged or included in error messages.

Note: Supabase's direct host is IPv6-only on the free plan.  If a network
lacks IPv6, set DATABASE_URL to the "Session pooler" string from the
Supabase dashboard (Connect button) instead.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import psycopg


class DatabaseConfigError(RuntimeError):
    pass


def connection_kwargs() -> dict[str, Any]:
    url = os.getenv("DATABASE_URL")
    if url:
        return {"conninfo": url, "connect_timeout": 15}

    supabase_url = os.getenv("SUPABASE_URL", "")
    password = os.getenv("SUPABASE_DB_PASSWORD", "")
    host = urlparse(supabase_url).hostname or ""
    if not host.endswith(".supabase.co") or not password or password == "replace_me":
        raise DatabaseConfigError(
            "Set DATABASE_URL, or SUPABASE_URL + SUPABASE_DB_PASSWORD, in .env"
        )
    ref = host.split(".")[0]
    return {
        "host": f"db.{ref}.supabase.co",
        "port": 5432,
        "dbname": "postgres",
        "user": "postgres",
        "password": password,
        "sslmode": "require",
        "connect_timeout": 15,
    }


def connect(*, autocommit: bool = True) -> psycopg.Connection[Any]:
    # Importing settings guarantees .env has been loaded.
    from app.core.config import settings  # noqa: F401

    return psycopg.connect(autocommit=autocommit, **connection_kwargs())
