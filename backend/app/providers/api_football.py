"""
Final Whistle — API-Football provider adapter.

Handles all communication with the API-Football (api-sports.io) service.
Every method returns raw or lightly typed data; normalization into
canonical domain models happens in the ingestion layer.

Docs: https://www.api-football.com/documentation-v3
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known competition IDs on API-Football for V1 competitions.
# These MUST be verified against real API responses during Milestone 0.
# ---------------------------------------------------------------------------
COMPETITION_IDS: dict[str, int] = {
    "EPL": 39,  # English Premier League
    "LA_LIGA": 140,  # La Liga
    "BUNDESLIGA": 78,  # Bundesliga
    "SERIE_A": 135,  # Serie A
    "UCL": 2,  # UEFA Champions League
}


class APIFootballClient:
    """Thin HTTP client for the API-Football v3 REST API."""

    def __init__(self, api_key: str, base_url: str = "https://v3.football.api-sports.io"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"x-apisports-key": self._api_key},
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Send a GET request and return the parsed JSON response.

        Raises on HTTP errors and logs quota information from response
        headers when available.
        """
        response = self._client.get(endpoint, params=params)
        response.raise_for_status()

        data: dict[str, Any] = response.json()

        # Log remaining quota from response headers (API-Sports convention)
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            logger.info("API-Football quota remaining: %s", remaining)

        errors = data.get("errors")
        if errors:
            logger.warning("API-Football returned errors: %s", errors)

        return data

    # ------------------------------------------------------------------
    # Endpoint methods
    # ------------------------------------------------------------------
    def get_status(self) -> dict[str, Any]:
        """Return account status including subscription and quota info."""
        return self._get("/status")

    def get_leagues(
        self, league_id: int | None = None, season: int | None = None
    ) -> dict[str, Any]:
        """Fetch league/competition metadata."""
        params: dict[str, Any] = {}
        if league_id is not None:
            params["id"] = league_id
        if season is not None:
            params["season"] = season
        return self._get("/leagues", params=params)

    def get_teams(self, league_id: int, season: int) -> dict[str, Any]:
        """Fetch teams for a competition season."""
        return self._get("/teams", params={"league": league_id, "season": season})

    def get_fixtures(
        self,
        league_id: int,
        season: int,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Fetch fixtures (scheduled and completed) for a competition season."""
        params: dict[str, Any] = {"league": league_id, "season": season}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if status:
            params["status"] = status
        return self._get("/fixtures", params=params)

    def get_standings(self, league_id: int, season: int) -> dict[str, Any]:
        """Fetch current standings/table for a competition season."""
        return self._get("/standings", params={"league": league_id, "season": season})

    def get_fixture_by_id(self, fixture_id: int) -> dict[str, Any]:
        """Fetch a single fixture by its API-Football ID."""
        return self._get("/fixtures", params={"id": fixture_id})

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> APIFootballClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
