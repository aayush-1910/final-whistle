"""
Final Whistle — FastAPI application entry point.

Read-only API over stored data and forecasts.  There are deliberately no
endpoints that trigger ingestion or simulations (README §14): those run from
the scripts in backend/scripts/.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool

from app.api import queries
from app.api.deps import create_pool, get_conn
from app.api.routes.v1 import router as v1_router
from app.api.schemas import HealthResponse


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    """``pool`` lets tests inject a pool bound to a throwaway schema."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = pool is None
        app.state.pool = pool or create_pool()
        app.state.pool.open(wait=False)
        try:
            yield
        finally:
            if owned:
                app.state.pool.close()

    app = FastAPI(
        title="Final Whistle",
        description=(
            "Football analytics and season-forecasting API (read-only). Forecasts are "
            "probabilities from a statistical model; every forecast states its model version, "
            "data cutoff and publication status."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    # CORS — the local Vite dev server during development.  Tighten for production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Liveness: the process is up.  Does not touch the database."""
        return HealthResponse(status="ok", service="final-whistle", database="not checked")

    @app.get("/api/v1/health/ready", response_model=HealthResponse, tags=["health"])
    def ready(conn: psycopg.Connection[Any] = Depends(get_conn)) -> HealthResponse:  # noqa: B008
        """Readiness: the database answers."""
        return HealthResponse(
            status="ok", service="final-whistle", database="ok" if queries.ping(conn) else "error"
        )

    app.include_router(v1_router)
    return app


app = create_app()
