"""Database connection pool and FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
from fastapi import HTTPException, Request
from psycopg_pool import ConnectionPool

from app.database.connection import connection_kwargs


def create_pool(
    *, search_path: str | None = None, min_size: int = 1, max_size: int = 5
) -> ConnectionPool:
    """A pool of autocommit connections.  ``search_path`` is for tests (throwaway schemas)."""
    kw = connection_kwargs()
    conninfo = kw.pop("conninfo", "")
    kw["autocommit"] = True
    if search_path:
        kw["options"] = f"-c search_path={search_path}"
    return ConnectionPool(
        conninfo=conninfo, kwargs=kw, min_size=min_size, max_size=max_size, open=False,
        name="final-whistle",
    )  # fmt: skip


def get_conn(request: Request) -> Iterator[psycopg.Connection[Any]]:
    pool: ConnectionPool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise HTTPException(503, "Database not configured")
    try:
        with pool.connection(timeout=10) as conn:
            yield conn
    except psycopg.OperationalError as e:
        raise HTTPException(503, f"Database unavailable: {type(e).__name__}") from None
