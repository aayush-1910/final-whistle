"""
Final Whistle — football-data.org (v4) provider adapter.

Returns raw provider JSON; normalization into domain models happens in the
ingestion layer.  The only provider-specific translation kept here is the
status mapping, so the rest of the app never sees provider status strings.

Docs (checked 2026-11-03):
  - Quickstart:  https://www.football-data.org/documentation/quickstart
  - Policies:    https://docs.football-data.org/general/v4/policies.html
      auth header "X-Auth-Token"; "10 requests/minute in the free plan"
  - Competition: https://docs.football-data.org/general/v4/competition.html
      /competitions/{code}/matches|standings|teams, `season` = 4-digit start year
  - Match:       https://docs.football-data.org/general/v4/match.html
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from app.domain.models import FixtureStatus

logger = logging.getLogger(__name__)

PROVIDER_NAME = "football_data_org"
BASE_URL = "https://api.football-data.org/v4"

# Competition codes.  PL, PD, BL1, SA appear in the official docs.
# "CL" is the expected Champions League code — VERIFY against a real
# /competitions response before relying on it.
COMPETITION_CODES: dict[str, str] = {
    "EPL": "PL",
    "LA_LIGA": "PD",
    "BUNDESLIGA": "BL1",
    "SERIE_A": "SA",
    "UCL": "CL",
}

# Status values verbatim from the Match resource docs.
STATUS_MAP: dict[str, FixtureStatus] = {
    "SCHEDULED": FixtureStatus.SCHEDULED,
    "TIMED": FixtureStatus.SCHEDULED,  # scheduled with a confirmed kickoff time
    "IN_PLAY": FixtureStatus.IN_PROGRESS,
    "PAUSED": FixtureStatus.IN_PROGRESS,  # e.g. half-time
    "FINISHED": FixtureStatus.FINISHED,
    "SUSPENDED": FixtureStatus.SUSPENDED,
    "POSTPONED": FixtureStatus.POSTPONED,
    "CANCELLED": FixtureStatus.CANCELLED,
    "AWARDED": FixtureStatus.AWARDED,
}


def normalize_status(provider_status: str | None) -> FixtureStatus:
    """Map a football-data.org status to the canonical status.

    Unrecognised values map to UNKNOWN (never silently to SCHEDULED/FINISHED)
    so they surface in validation instead of corrupting a simulation.
    """
    if provider_status is None:
        return FixtureStatus.UNKNOWN
    status = STATUS_MAP.get(provider_status.upper())
    if status is None:
        logger.warning("Unrecognised football-data.org status: %r", provider_status)
        return FixtureStatus.UNKNOWN
    return status


class FootballDataOrgError(RuntimeError):
    """Raised for any non-success response, including plan restrictions.

    Raising (rather than returning an empty payload) guarantees that
    "access denied" can never be mistaken for "no data exists".
    """

    def __init__(self, status_code: int, message: str, endpoint: str):
        super().__init__(f"{endpoint} -> HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint


class RateLimiter:
    """Sliding-window limiter: at most `max_calls` per `period` seconds."""

    def __init__(
        self,
        max_calls: int,
        period: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_calls = max_calls
        self.period = period
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        while self._calls and now - self._calls[0] >= self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            wait = self.period - (now - self._calls[0])
            if wait > 0:
                logger.info("Rate limit reached; sleeping %.1fs", wait)
                self._sleep(wait)
            self._calls.popleft()
        self._calls.append(self._clock())


class FootballDataOrgClient:
    """Thin HTTP client for the football-data.org v4 API."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = BASE_URL,
        max_calls_per_minute: int = 10,
        transport: httpx.BaseTransport | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Auth-Token": api_token},
            timeout=30.0,
            transport=transport,
        )
        self._limiter = rate_limiter or RateLimiter(max_calls_per_minute, 60.0)
        self.request_count = 0

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._limiter.acquire()
        self.request_count += 1
        response = self._client.get(endpoint, params=params)

        for header in ("X-Requests-Available-Minute", "X-RequestCounter-Reset"):
            if header in response.headers:
                logger.debug("%s: %s", header, response.headers[header])

        if response.status_code != 200:
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise FootballDataOrgError(response.status_code, str(message), endpoint)

        data: dict[str, Any] = response.json()
        return data

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def get_competitions(self) -> dict[str, Any]:
        """List competitions available to this token."""
        return self._get("/competitions")

    def get_competition(self, code: str) -> dict[str, Any]:
        """Competition metadata, including its list of seasons."""
        return self._get(f"/competitions/{code}")

    def get_teams(self, code: str, season: int) -> dict[str, Any]:
        return self._get(f"/competitions/{code}/teams", {"season": season})

    def get_matches(
        self,
        code: str,
        season: int,
        *,
        status: str | None = None,
        matchday: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"season": season}
        if status:
            params["status"] = status
        if matchday is not None:
            params["matchday"] = matchday
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        return self._get(f"/competitions/{code}/matches", params)

    def get_standings(self, code: str, season: int) -> dict[str, Any]:
        return self._get(f"/competitions/{code}/standings", {"season": season})

    # ------------------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FootballDataOrgClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
