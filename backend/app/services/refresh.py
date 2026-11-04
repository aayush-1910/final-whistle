"""
The scheduled refresh: import → forecast → publish, for the current season.

  1. Import the latest fixtures/results for each competition (football-data.org).
  2. Re-forecast a competition only when something changed since its latest
     forecast (any fixture in any competition: the model is fitted on all of
     them), or when its latest forecast is older than ``max_age``, or ``force``.
  3. Publish each new run through the same quality gates as publish_run.py.

Every step is reported (ok / skipped / failed, with the reason). One
competition failing never stops the others; the caller turns any failure into
a non-zero exit code so a scheduler flags it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from app.database import publishing
from app.database.forecasts import git_commit
from app.ingestion.service import IngestionResult
from app.models import config
from app.models.data import load_match_records
from app.models.poisson import PoissonModel, fit_poisson
from app.services.forecasting import save_run, simulate_competition

log = logging.getLogger("final_whistle.refresh")

COMPETITIONS = ("EPL", "LA_LIGA", "BUNDESLIGA", "SERIE_A", "UCL")


@dataclass
class Step:
    competition: str
    step: str  # import / forecast / publish
    status: str  # ok / skipped / failed
    detail: str = ""
    run_id: int | None = None
    seconds: float = 0.0


@dataclass
class RefreshReport:
    started_at: datetime
    season: int
    steps: list[Step] = field(default_factory=list)
    api_requests: int = 0
    finished_at: datetime | None = None

    @property
    def failed(self) -> bool:
        return any(s.status == "failed" for s in self.steps)

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        level = logging.ERROR if step.status == "failed" else logging.INFO
        log.log(
            level,
            "%s %s %s: %s",
            step.competition,
            step.step,
            step.status,
            step.detail,
            extra={"refresh_step": asdict(step)},
        )
        return step

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "season": self.season,
            "failed": self.failed,
            "api_requests": self.api_requests,
            "steps": [asdict(s) for s in self.steps],
        }


def _latest_current_run(conn: psycopg.Connection[Any], comp: str, season: int) -> datetime | None:
    row = conn.execute(
        """select max(r.data_cutoff) from model_runs r join seasons s on s.id = r.season_id
             join competitions c on c.id = r.competition_id
            where c.code = %s and s.start_year = %s and not r.is_backfill
              and r.status = 'completed' and r.model_version = %s""",
        (comp, season, config.MODEL_VERSION),
    ).fetchone()
    return row[0] if row else None


def _last_fixture_change(conn: psycopg.Connection[Any]) -> datetime | None:
    row = conn.execute("select max(updated_at) from fixtures").fetchone()
    return row[0] if row else None


def forecast_reason(
    latest_run: datetime | None,
    last_change: datetime | None,
    now: datetime,
    *,
    force: bool,
    max_age: timedelta,
) -> str | None:
    """Why a new forecast is needed, or None if the latest one is still current."""
    if force:
        return "forced"
    if latest_run is None:
        return f"no forecast with model {config.MODEL_VERSION} yet"
    if last_change is not None and last_change > latest_run:
        return "new or changed fixtures since the last forecast"
    if now - latest_run > max_age:
        return f"last forecast is older than {max_age.days} days"
    return None


def refresh(
    conn: psycopg.Connection[Any],
    ingest: Callable[[str, int], IngestionResult] | None,
    *,
    season: int = 2026,
    competitions: Sequence[str] = COMPETITIONS,
    n_sims: int = 10_000,
    seed: int = 20261103,
    force: bool = False,
    publish: bool = True,
    max_age: timedelta = timedelta(days=7),
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> RefreshReport:
    """``ingest(code, season)`` imports one competition-season (None = skip importing)."""
    report = RefreshReport(started_at=now(), season=season)
    import_failed: set[str] = set()

    # 1. Import -------------------------------------------------------------------
    for comp in competitions:
        if ingest is None:
            report.add(Step(comp, "import", "skipped", "import disabled"))
            continue
        t0 = time.monotonic()
        try:
            r = ingest(comp, season)
        except Exception as e:  # noqa: BLE001 - reported, never swallowed silently
            import_failed.add(comp)
            report.add(
                Step(
                    comp,
                    "import",
                    "failed",
                    f"{type(e).__name__}: {e}"[:500],
                    seconds=time.monotonic() - t0,
                )
            )
            continue
        report.api_requests += r.requests
        cons = r.consistency
        detail = f"+{r.inserted} new, {r.updated} updated"
        if cons is not None and not cons.get("ok", True):
            detail += f"; table check: {len(cons.get('discrepancies', []))} differences"
        if r.status == "failed":
            import_failed.add(comp)
            report.add(
                Step(
                    comp,
                    "import",
                    "failed",
                    r.error or "import failed",
                    seconds=time.monotonic() - t0,
                )
            )
        else:
            if r.status == "partial":
                detail += f"; {len(r.issues)} records skipped"
            report.add(Step(comp, "import", "ok", detail, seconds=time.monotonic() - t0))

    # 2. Decide which competitions need a new forecast ------------------------------
    # Data cutoff from the DATABASE clock: import timestamps come from it too, and a
    # machine whose clock runs behind would otherwise produce a cutoff "before" the
    # import it just made (the publishing gate then rightly refuses the run).
    db_now = conn.execute("select now()").fetchone()
    as_of = max(now(), db_now[0]) if db_now else now()
    last_change = _last_fixture_change(conn)
    todo: list[tuple[str, str]] = []
    for comp in competitions:
        if comp in import_failed:
            report.add(
                Step(comp, "forecast", "skipped", "import failed; keeping the previous forecast")
            )
            continue
        reason = forecast_reason(
            _latest_current_run(conn, comp, season),
            last_change,
            as_of,
            force=force,
            max_age=max_age,
        )
        if reason is None:
            report.add(Step(comp, "forecast", "skipped", "no new results since the last forecast"))
        else:
            todo.append((comp, reason))

    # 3. Forecast (one model fit for all) and publish ---------------------------------
    if todo:
        t0 = time.monotonic()
        records = load_match_records(conn)
        model: PoissonModel = fit_poisson(records, as_of, config.POISSON)
        fit_seconds = time.monotonic() - t0
        log.info("model fitted on %d matches in %.1fs", model.matches_used, fit_seconds)
        code_version = git_commit()
        for comp, reason in todo:
            t0 = time.monotonic()
            try:
                forecast, rules = simulate_competition(
                    conn, records, model, comp, season, as_of, n_sims=n_sims, seed=seed
                )
                run_id = save_run(conn, forecast, model, rules, code_version=code_version)
            except Exception as e:  # noqa: BLE001
                report.add(
                    Step(
                        comp,
                        "forecast",
                        "failed",
                        f"{type(e).__name__}: {e}"[:500],
                        seconds=time.monotonic() - t0,
                    )
                )
                continue
            report.add(
                Step(
                    comp,
                    "forecast",
                    "ok",
                    f"{reason}; {forecast.completed_matches} played, "
                    f"{len(forecast.matches)} simulated",
                    run_id,
                    time.monotonic() - t0,
                )
            )
            if not publish:
                report.add(Step(comp, "publish", "skipped", "publishing disabled", run_id))
                continue
            _, checks = publishing.publish_checks(conn, run_id)
            failing = [c for c in checks if not c.ok]
            if failing:
                report.add(
                    Step(
                        comp,
                        "publish",
                        "failed",
                        "; ".join(f"{c.name} ({c.detail})" for c in failing),
                        run_id,
                    )
                )
            else:
                publishing.publish(conn, run_id)
                report.add(Step(comp, "publish", "ok", "all quality checks passed", run_id))

    report.finished_at = now()
    return report
