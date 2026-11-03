"""Tests for the football-data.org adapter. No network: uses httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest

from app.domain.models import FixtureStatus
from app.providers.football_data_org import (
    STATUS_MAP,
    FootballDataOrgClient,
    FootballDataOrgError,
    RateLimiter,
    normalize_status,
)


# ---------------------------------------------------------------------------
# Status normalization
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SCHEDULED", FixtureStatus.SCHEDULED),
        ("TIMED", FixtureStatus.SCHEDULED),
        ("IN_PLAY", FixtureStatus.IN_PROGRESS),
        ("PAUSED", FixtureStatus.IN_PROGRESS),
        ("FINISHED", FixtureStatus.FINISHED),
        ("SUSPENDED", FixtureStatus.SUSPENDED),
        ("POSTPONED", FixtureStatus.POSTPONED),
        ("CANCELLED", FixtureStatus.CANCELLED),
        ("AWARDED", FixtureStatus.AWARDED),
        ("finished", FixtureStatus.FINISHED),
    ],
)
def test_normalize_known_statuses(raw: str, expected: FixtureStatus) -> None:
    assert normalize_status(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "LIVE", "SOMETHING_NEW"])
def test_unknown_status_never_guessed(raw: str | None) -> None:
    assert normalize_status(raw) == FixtureStatus.UNKNOWN


def test_all_documented_statuses_mapped() -> None:
    documented = {"SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "FINISHED",
                  "SUSPENDED", "POSTPONED", "CANCELLED", "AWARDED"}
    assert set(STATUS_MAP) == documented


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
class _NoWaitLimiter(RateLimiter):
    def __init__(self) -> None:
        super().__init__(1000, 60.0)


def _client(handler) -> FootballDataOrgClient:  # type: ignore[no-untyped-def]
    return FootballDataOrgClient(
        "test-token",
        transport=httpx.MockTransport(handler),
        rate_limiter=_NoWaitLimiter(),
    )


def test_sends_auth_header_and_season_param() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("X-Auth-Token")
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"matches": []})

    with _client(handler) as c:
        c.get_matches("PL", 2026, status="FINISHED", date_from="2026-08-01")

    assert seen["token"] == "test-token"
    assert seen["path"] == "/v4/competitions/PL/matches"
    assert seen["params"] == {"season": "2026", "status": "FINISHED", "dateFrom": "2026-08-01"}


@pytest.mark.parametrize("code", [400, 403, 404, 429, 500])
def test_error_responses_raise_not_return_empty(code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"message": "restricted resource", "errorCode": code})

    with _client(handler) as c, pytest.raises(FootballDataOrgError) as exc:
        c.get_standings("PL", 2010)

    assert exc.value.status_code == code
    assert "restricted resource" in exc.value.message


def test_request_count_tracked() -> None:
    with _client(lambda r: httpx.Response(200, json={})) as c:
        c.get_competition("PL")
        c.get_teams("PL", 2026)
        assert c.request_count == 2


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def test_rate_limiter_sleeps_when_window_full() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(3, 60.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.acquire()
        now[0] += 1.0
    assert slept == []

    limiter.acquire()  # 4th call at t=3 must wait until t=60
    assert slept == [pytest.approx(57.0)]


def test_rate_limiter_no_sleep_after_window_expires() -> None:
    now = [0.0]
    slept: list[float] = []
    limiter = RateLimiter(2, 60.0, clock=lambda: now[0], sleep=slept.append)
    limiter.acquire()
    limiter.acquire()
    now[0] = 61.0
    limiter.acquire()
    assert slept == []
