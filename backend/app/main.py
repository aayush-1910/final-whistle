"""
Final Whistle — FastAPI application entry point.

Read-only API over stored data and forecasts.  There are deliberately no
endpoints that trigger ingestion or simulations (README §14): those run from
the scripts in backend/scripts/.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool

from app.api import queries
from app.api.deps import create_pool, get_conn
from app.api.routes.v1 import router as v1_router
from app.api.schemas import HealthResponse
from app.core.config import settings
from app.core.logging import setup_logging

log = logging.getLogger("final_whistle.api")


def create_app(pool: ConnectionPool | None = None) -> FastAPI:
    """``pool`` lets tests inject a pool bound to a throwaway schema."""
    setup_logging()

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
    # CORS: only the dashboard's own origins (CORS_ORIGINS), read-only methods.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        # Errors and slow requests are logged at WARNING so they stand out.
        level = logging.WARNING if response.status_code >= 500 or ms > 3000 else logging.INFO
        log.log(level, "%s %s %d %.0fms", request.method, request.url.path, response.status_code,
                ms, extra={"method": request.method, "path": request.url.path,
                           "status": response.status_code, "ms": round(ms)})  # fmt: skip
        # Data changes at most a few times a day: let browsers/CDNs cache briefly.
        # Health checks are never cached: a monitor must see the current state.
        if request.url.path.startswith("/api/v1/health"):
            response.headers["Cache-Control"] = "no-store"
        elif request.method == "GET" and response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=60")
        return response

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
