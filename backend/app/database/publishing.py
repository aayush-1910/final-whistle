"""
Publishing gates (README §1, §15): a forecast run becomes visible through the API
only if every check passes.

  1. the run completed and is not already published
  2. its model version is the current production version (models/config.py)
  3. stored backtests exist (match-level and season-level)
  4. the competition's rules come from a PRIMARY source, or secondary-sourced rules
     are explicitly accepted
  5. data: a current run must have used the latest import (cutoff after it); a
     historical backfill run must describe the past (cutoff before the latest import)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from app.models import config
from app.simulations.rules import RulesNotFoundError, load_rules

# Competition-seasons whose secondary-sourced rules the project owner has reviewed and
# accepted (2026-11-04: La Liga and Serie A rules verified via Wikipedia summaries of the
# official regulations). These publish without --accept-secondary-rules.
ACCEPTED_SECONDARY_RULES: frozenset[tuple[str, int]] = frozenset(
    {("LA_LIGA", 2026), ("SERIE_A", 2026)}
)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class RunState:
    run_id: int
    competition: str
    season: int
    model_version: str
    data_cutoff: datetime
    is_published: bool
    is_backfill: bool


def run_state(conn: psycopg.Connection[Any], run_id: int) -> RunState | None:
    row = conn.execute(
        """select r.id, c.code, s.start_year, r.model_version, r.data_cutoff, r.is_published,
                  r.is_backfill
             from model_runs r join competitions c on c.id = r.competition_id
             join seasons s on s.id = r.season_id where r.id = %s""",
        (run_id,),
    ).fetchone()
    return RunState(*row) if row else None


def publish_checks(
    conn: psycopg.Connection[Any], run_id: int, *, accept_secondary_rules: bool = False
) -> tuple[RunState, list[Check]]:
    state = run_state(conn, run_id)
    if state is None:
        raise LookupError(f"Run {run_id} not found")
    status, last_import = conn.execute(
        """select r.status,
                  (select max(finished_at) from ingestion_runs i
                    where i.competition_id = r.competition_id
                      and i.status in ('succeeded', 'partial'))
             from model_runs r where r.id = %s""",
        (run_id,),
    ).fetchone()  # type: ignore[misc]
    backtests = dict(
        conn.execute("select kind, max(model_version) from backtest_runs group by kind").fetchall()
    )
    try:
        quality: str | None = load_rules(state.competition, state.season).source_quality
    except RulesNotFoundError:
        quality = None
    owner_accepted = (state.competition, state.season) in ACCEPTED_SECONDARY_RULES
    secondary_ok = quality == "secondary" and (accept_secondary_rules or owner_accepted)
    how = (
        "accepted by the project owner"
        if owner_accepted
        else "accepted via --accept-secondary-rules"
    )
    cutoff = state.data_cutoff
    if state.is_backfill:
        data_check = Check(
            "historical run describes the past",
            last_import is not None and cutoff <= last_import,
            f"backfill, cutoff {cutoff:%Y-%m-%d %H:%M}",
        )
    else:
        data_check = Check(
            "used the latest imported data",
            last_import is None or cutoff >= last_import,
            f"cutoff {cutoff:%Y-%m-%d %H:%M}, last import {last_import:%Y-%m-%d %H:%M}"
            if last_import
            else "no import",
        )
    checks = [
        Check("run completed", status == "completed", status),
        Check("not already published", not state.is_published,
              "already published" if state.is_published else "ok"),
        Check("current model version", state.model_version == config.MODEL_VERSION,
              f"run {state.model_version}, production {config.MODEL_VERSION}"),
        Check("match-level backtest stored", "match" in backtests,
              f"latest for {backtests.get('match')}"),
        Check("season-level backtest stored", "season" in backtests,
              f"latest for {backtests.get('season')}"),
        Check("rules from a primary source", quality == "primary" or secondary_ok,
              f"{quality}" + (f" ({how})" if secondary_ok else "")),
        data_check,
    ]  # fmt: skip
    return state, checks


def publish(conn: psycopg.Connection[Any], run_id: int) -> None:
    conn.execute("update model_runs set is_published = true where id = %s", (run_id,))


def unpublish(conn: psycopg.Connection[Any], run_id: int) -> None:
    conn.execute("update model_runs set is_published = false where id = %s", (run_id,))
