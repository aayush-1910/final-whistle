"""
Read-only queries behind the API.  All SQL is parameterised; nothing here writes.

Publication rule: forecast queries return only ``is_published`` runs unless
``preview`` is True, in which case the latest run is returned regardless and
its ``is_published`` flag tells the client it is a preview.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from app.api import schemas as s
from app.models.poisson import score_matrix
from app.simulations.rules import RulesNotFoundError, load_rules

Conn = psycopg.Connection[Any]
STALE_AFTER_HOURS = 48
_UCL_ROUNDS = ["round_of_16", "quarter_finals", "semi_finals", "final", "winner"]


class NotFoundError(LookupError):
    pass


def season_label(year: int) -> str:
    return f"{year}/{(year + 1) % 100:02d}"


def _team(row: dict[str, Any], prefix: str = "") -> s.TeamRef:
    return s.TeamRef(
        id=row[f"{prefix}id"], name=row[f"{prefix}name"],
        short_name=row[f"{prefix}short_name"], tla=row[f"{prefix}tla"],
    )  # fmt: skip


def _rows(conn: Conn, sql: str, params: Any = ()) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        return list(cur.execute(sql, params).fetchall())


def _one(conn: Conn, sql: str, params: Any = ()) -> dict[str, Any] | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ping(conn: Conn) -> bool:
    return conn.execute("select 1").fetchone() == (1,)


# ---------------------------------------------------------------------------
# Competitions, seasons, freshness
# ---------------------------------------------------------------------------
def competition(conn: Conn, code: str) -> dict[str, Any]:
    row = _one(
        conn, "select id, code, name, format, country from competitions where code = %s", (code,)
    )
    if row is None:
        raise NotFoundError(f"Unknown competition {code!r}")
    return row


def season_id(conn: Conn, competition_id: int, year: int) -> int:
    row = _one(conn, "select id from seasons where competition_id = %s and start_year = %s",
               (competition_id, year))  # fmt: skip
    if row is None:
        raise NotFoundError(f"No season {season_label(year)} for this competition")
    return int(row["id"])


def freshness(conn: Conn, competition_id: int, now: datetime | None = None) -> s.Freshness:
    row = _one(
        conn,
        """select finished_at, status from ingestion_runs
            where competition_id = %s and status in ('succeeded', 'partial')
            order by finished_at desc nulls last limit 1""",
        (competition_id,),
    )
    return _freshness(row["finished_at"] if row else None, row["status"] if row else None,
                      now or datetime.now(tz=UTC))  # fmt: skip


def _rules_quality(code: str, year: int) -> str | None:
    try:
        return load_rules(code, year).source_quality
    except RulesNotFoundError:
        return None


def _run_info(row: dict[str, Any], code: str, year: int) -> s.RunInfo:
    return s.RunInfo(
        run_id=row["id"], model_name=row["model_name"], model_version=row["model_version"],
        data_cutoff=row["data_cutoff"], run_at=row["run_at"],
        simulation_count=row["simulation_count"], seed=row["seed"],
        code_version=row["code_version"], is_published=row["is_published"],
        rules_source_quality=_rules_quality(code, year), notes=list(row["notes"] or []),
    )  # fmt: skip


_RUN_FIELDS = ("id", "model_name", "model_version", "data_cutoff", "run_at", "simulation_count",
               "seed", "code_version", "is_published", "notes")  # fmt: skip
_RUN_COLS = ", ".join(f"r.{c}" for c in _RUN_FIELDS)


def latest_run(conn: Conn, season: int, *, preview: bool) -> dict[str, Any] | None:
    return _one(
        conn,
        f"""select {_RUN_COLS} from model_runs r
             where r.season_id = %s and r.status = 'completed' and (r.is_published or %s)
             order by r.run_at desc, r.id desc limit 1""",
        (season, preview),
    )


def _freshness(last: datetime | None, status: str | None, now: datetime) -> s.Freshness:
    return s.Freshness(
        last_ingested_at=last,
        last_ingestion_status=status,
        is_stale=last is None or now - last > timedelta(hours=STALE_AFTER_HOURS),
        stale_after_hours=STALE_AFTER_HOURS,
    )


def list_competitions(conn: Conn, now: datetime | None = None) -> list[s.CompetitionSummary]:
    """One round trip: competitions + current season + freshness + latest runs."""
    now = now or datetime.now(tz=UTC)
    rows = _rows(
        conn,
        f"""select c.code, c.name, c.format, c.country, se.start_year, ir.finished_at, ir.status,
                   (pr.id is not null) as has_preview, pr.is_published as preview_is_published,
                   {", ".join(f"r.{col} as pub_{col}" for col in _RUN_FIELDS)}
              from competitions c
              left join lateral (select id, start_year from seasons where competition_id = c.id
                                  order by start_year desc limit 1) se on true
              left join lateral (select finished_at, status from ingestion_runs
                                  where competition_id = c.id and status in ('succeeded', 'partial')
                                  order by finished_at desc nulls last limit 1) ir on true
              left join lateral (select * from model_runs where season_id = se.id
                                    and status = 'completed' and is_published
                                  order by run_at desc, id desc limit 1) r on true
              left join lateral (select id, is_published from model_runs where season_id = se.id
                                    and status = 'completed'
                                  order by run_at desc, id desc limit 1) pr on true
             order by c.id""",
    )
    out = []
    for row in rows:
        year = row["start_year"]
        run = {col: row[f"pub_{col}"] for col in _RUN_FIELDS} if row["pub_id"] is not None else None
        out.append(
            s.CompetitionSummary(
                code=row["code"], name=row["name"], format=row["format"], country=row["country"],
                current_season=year, season_label=season_label(year) if year else None,
                freshness=_freshness(row["finished_at"], row["status"], now),
                latest_published_run=_run_info(run, row["code"], year) if run and year else None,
                preview_run_available=bool(row["has_preview"]) and not row["preview_is_published"],
            )
        )  # fmt: skip
    return out


# ---------------------------------------------------------------------------
# Standings (computed from results; provider standings are not trusted for order)
# ---------------------------------------------------------------------------
_ORDERING_NOTE = (
    "Computed from match results. Ordered by points, goal difference, goals scored; the "
    "competition's full tiebreakers (e.g. head-to-head) apply to the final table and are used "
    "in the forecasts."
)


def _tables(conn: Conn, season_ids: list[int]) -> dict[int, list[s.StandingRow]]:
    """Current tables for several seasons in ONE query (league phase for the UCL)."""
    if not season_ids:
        return {}
    rows = _rows(
        conn,
        """select f.season_id, c.code, se.start_year, f.status, f.home_score, f.away_score,
                  h.id as h_id, h.name as h_name, h.short_name as h_short_name, h.tla as h_tla,
                  a.id as a_id, a.name as a_name, a.short_name as a_short_name, a.tla as a_tla
             from fixtures f
             join seasons se on se.id = f.season_id
             join competitions c on c.id = se.competition_id
             join teams h on h.id = f.home_team_id
             join teams a on a.id = f.away_team_id
            where f.season_id = any(%s)
              and f.stage = case when c.code = 'UCL' then 'league_stage' else 'regular_season' end
            order by f.kickoff_utc, f.id""",
        (season_ids,),
    )
    teams: dict[int, dict[int, s.TeamRef]] = defaultdict(dict)
    tot: dict[int, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    form: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    points: dict[int, tuple[int, int]] = {}
    for r in rows:
        sid = r["season_id"]
        teams[sid][r["h_id"]] = _team(r, "h_")
        teams[sid][r["a_id"]] = _team(r, "a_")
        if sid not in points:
            rules = (
                load_rules(r["code"], r["start_year"])
                if _rules_quality(r["code"], r["start_year"])
                else None
            )
            points[sid] = (rules.points_for_win, rules.points_for_draw) if rules else (3, 1)
        if r["status"] not in ("finished", "awarded"):
            continue
        w, d = points[sid]
        for team, gf, ga in ((r["h_id"], r["home_score"], r["away_score"]),
                             (r["a_id"], r["away_score"], r["home_score"])):  # fmt: skip
            x = tot[sid][team]
            x["played"] += 1
            x["goals_for"] += gf
            x["goals_against"] += ga
            res = "W" if gf > ga else "D" if gf == ga else "L"
            x["won" if res == "W" else "drawn" if res == "D" else "lost"] += 1
            x["points"] += w if res == "W" else d if res == "D" else 0
            form[sid][team].append(res)
    out: dict[int, list[s.StandingRow]] = {}
    for sid, ts in teams.items():
        tt = tot[sid]

        def key(
            t: int, tt: dict[int, dict[str, int]] = tt, ts: dict[int, s.TeamRef] = ts
        ) -> tuple[int, int, int, str]:
            x = tt[t]
            return (
                -x["points"],
                -(x["goals_for"] - x["goals_against"]),
                -x["goals_for"],
                ts[t].name,
            )

        order = sorted(ts, key=key)
        out[sid] = [
            s.StandingRow(
                position=i, team=ts[t], played=tt[t]["played"], won=tt[t]["won"],
                drawn=tt[t]["drawn"], lost=tt[t]["lost"], goals_for=tt[t]["goals_for"],
                goals_against=tt[t]["goals_against"],
                goal_difference=tt[t]["goals_for"] - tt[t]["goals_against"],
                points=tt[t]["points"], form=form[sid][t][-5:],
            )
            for i, t in enumerate(order, start=1)
        ]  # fmt: skip
    return out


def standings(conn: Conn, code: str, year: int) -> s.StandingsResponse:
    c = competition(conn, code)
    sid = season_id(conn, c["id"], year)
    return s.StandingsResponse(
        competition=code, season=year, season_label=season_label(year),
        ordering_note=_ORDERING_NOTE, freshness=freshness(conn, c["id"]),
        rows=_tables(conn, [sid]).get(sid, []),
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Season forecasts
# ---------------------------------------------------------------------------
def _team_forecasts(conn: Conn, run_id: int, ucl: bool) -> list[s.TeamForecast]:
    rows = _rows(
        conn,
        """select t.id, t.name, t.short_name, t.tla, f.current_points, f.played, f.expected_points,
                  f.expected_position, f.position_probs, f.zone_probs, f.round_probs
             from season_forecasts f join teams t on t.id = f.team_id
            where f.model_run_id = %s""",
        (run_id,),
    )
    out = [
        s.TeamForecast(
            team=_team(r), current_points=r["current_points"], played=r["played"],
            expected_points=r["expected_points"], expected_position=r["expected_position"],
            position_probs=list(r["position_probs"]), zone_probs=r["zone_probs"],
            round_probs=r["round_probs"],
        )
        for r in rows
    ]  # fmt: skip
    if ucl:
        return sorted(
            out, key=lambda t: (-(t.round_probs or {}).get("winner", 0.0), t.expected_position)
        )
    return sorted(out, key=lambda t: t.expected_position)


def season_forecast(conn: Conn, code: str, year: int, *, preview: bool) -> s.SeasonForecastResponse:
    c = competition(conn, code)
    sid = season_id(conn, c["id"], year)
    run = latest_run(conn, sid, preview=preview)
    if run is None:
        raise NotFoundError(
            "No published forecast for this season yet"
            + ("" if preview else " (use ?preview=true to see the latest unpublished run)")
        )
    zones: list[s.Zone] = []
    with contextlib.suppress(RulesNotFoundError):
        zones = [
            s.Zone(key=z.key, label=z.label, first_position=z.first_position,
                   last_position=z.last_position)
            for z in load_rules(code, year).zones
        ]  # fmt: skip
    return s.SeasonForecastResponse(
        competition=code, season=year, season_label=season_label(year),
        run=_run_info(run, code, year), freshness=freshness(conn, c["id"]), zones=zones,
        rounds=_UCL_ROUNDS if code == "UCL" else None,
        teams=_team_forecasts(conn, run["id"], code == "UCL"),
    )  # fmt: skip


def forecast_run(conn: Conn, run_id: int) -> s.ForecastRunResponse:
    row = _one(
        conn,
        f"""select {_RUN_COLS}, c.code, se.start_year from model_runs r
              join competitions c on c.id = r.competition_id join seasons se on se.id = r.season_id
             where r.id = %s""",
        (run_id,),
    )
    if row is None:
        raise NotFoundError(f"No forecast run {run_id}")
    return s.ForecastRunResponse(
        competition=row["code"], season=row["start_year"],
        run=_run_info(row, row["code"], row["start_year"]),
        teams=_team_forecasts(conn, run_id, row["code"] == "UCL"),
    )  # fmt: skip


def team_forecast_history(
    conn: Conn, team_id: int, code: str, year: int, *, preview: bool
) -> s.TeamForecastHistory:
    c = competition(conn, code)
    sid = season_id(conn, c["id"], year)
    team = team_ref(conn, team_id)
    rows = _rows(
        conn,
        """select r.id, r.run_at, r.data_cutoff, r.model_version, r.is_published,
                  f.expected_position, f.expected_points, f.zone_probs, f.round_probs
             from season_forecasts f join model_runs r on r.id = f.model_run_id
            where f.team_id = %s and r.season_id = %s and (r.is_published or %s)
            order by r.run_at""",
        (team_id, sid, preview),
    )
    return s.TeamForecastHistory(
        team=team, competition=code, season=year,
        points=[
            s.ForecastHistoryPoint(
                run_id=r["id"], run_at=r["run_at"], data_cutoff=r["data_cutoff"],
                model_version=r["model_version"], is_published=r["is_published"],
                expected_position=r["expected_position"], expected_points=r["expected_points"],
                zone_probs=r["zone_probs"], round_probs=r["round_probs"],
            )
            for r in rows
        ],
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_FIXTURE_SELECT = """
    select f.id, c.code, se.start_year, f.stage, f.matchday, f.kickoff_utc, f.status,
           f.home_score, f.away_score, f.duration, f.home_penalties, f.away_penalties,
           h.id as h_id, h.name as h_name, h.short_name as h_short_name, h.tla as h_tla,
           a.id as a_id, a.name as a_name, a.short_name as a_short_name, a.tla as a_tla,
           mf.p_home, mf.p_draw, mf.p_away, mf.xg_home, mf.xg_away,
           mr.id as run_id, mr.model_version, mr.data_cutoff, mr.is_published
      from fixtures f
      join seasons se on se.id = f.season_id
      join competitions c on c.id = se.competition_id
      join teams h on h.id = f.home_team_id
      join teams a on a.id = f.away_team_id
      left join lateral (
            select r.id, r.model_version, r.data_cutoff, r.is_published from model_runs r
             where r.season_id = f.season_id and r.status = 'completed'
               and (r.is_published or %(preview)s)
               and exists (select 1 from match_forecasts m
                            where m.model_run_id = r.id and m.fixture_id = f.id)
             order by r.run_at desc, r.id desc limit 1) mr on true
      left join match_forecasts mf on mf.model_run_id = mr.id and mf.fixture_id = f.id
"""


def _fixture(r: dict[str, Any]) -> s.FixtureOut:
    fc = None
    if r["run_id"] is not None and r["p_home"] is not None:
        fc = s.MatchForecastOut(
            p_home=r["p_home"], p_draw=r["p_draw"], p_away=r["p_away"], xg_home=r["xg_home"],
            xg_away=r["xg_away"], run_id=r["run_id"], model_version=r["model_version"],
            data_cutoff=r["data_cutoff"], is_published=r["is_published"],
        )  # fmt: skip
    return s.FixtureOut(
        id=r["id"], competition=r["code"], season=r["start_year"], stage=r["stage"],
        matchday=r["matchday"], kickoff_utc=r["kickoff_utc"], status=r["status"],
        home=_team(r, "h_"), away=_team(r, "a_"), home_score=r["home_score"],
        away_score=r["away_score"], duration=r["duration"], home_penalties=r["home_penalties"],
        away_penalties=r["away_penalties"], forecast=fc,
    )  # fmt: skip


def upcoming_fixtures(conn: Conn, *, days: int, competition_code: str | None, preview: bool,
                      now: datetime | None = None) -> list[s.FixtureOut]:  # fmt: skip
    now = now or datetime.now(tz=UTC)
    rows = _rows(
        conn,
        _FIXTURE_SELECT
        + """ where f.status in ('scheduled', 'postponed') and f.kickoff_utc >= %(now)s
                and f.kickoff_utc < %(until)s and (%(code)s::text is null or c.code = %(code)s)
              order by f.kickoff_utc, f.id""",
        {
            "preview": preview,
            "now": now,
            "until": now + timedelta(days=days),
            "code": competition_code,
        },
    )
    return [_fixture(r) for r in rows]


def fixture_detail(conn: Conn, fixture_id: int, *, preview: bool) -> s.FixtureDetail:
    r = _one(conn, _FIXTURE_SELECT + " where f.id = %(id)s", {"preview": preview, "id": fixture_id})
    if r is None:
        raise NotFoundError(f"No fixture {fixture_id}")
    base = _fixture(r)
    lines: list[s.Scoreline] = []
    grid = None
    if base.forecast is not None:
        m = score_matrix(base.forecast.xg_home, base.forecast.xg_away, 10)
        top = sorted(((m[i, j], i, j) for i in range(11) for j in range(11)), reverse=True)[:10]
        lines = [s.Scoreline(home=i, away=j, probability=float(p)) for p, i, j in top]
        grid = [[float(m[i, j]) for j in range(6)] for i in range(6)]
    return s.FixtureDetail(**base.model_dump(), likely_scorelines=lines, score_matrix=grid)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
def team_ref(conn: Conn, team_id: int) -> s.TeamRef:
    r = _one(conn, "select id, name, short_name, tla from teams where id = %s", (team_id,))
    if r is None:
        raise NotFoundError(f"No team {team_id}")
    return _team(r)


def team_detail(
    conn: Conn, team_id: int, *, preview: bool, now: datetime | None = None
) -> s.TeamDetail:
    now = now or datetime.now(tz=UTC)
    t = _one(conn, "select id, name, short_name, tla, country from teams where id = %s", (team_id,))
    if t is None:
        raise NotFoundError(f"No team {team_id}")
    memberships = _rows(
        conn,
        """select se.id, c.code, se.start_year from season_teams st
             join seasons se on se.id = st.season_id join competitions c on c.id = se.competition_id
            where st.team_id = %s order by se.start_year desc, c.id""",
        (team_id,),
    )
    tables = _tables(conn, [m["id"] for m in memberships])
    seasons = []
    for m in memberships:
        row = next((x for x in tables.get(m["id"], []) if x.team.id == team_id), None)
        seasons.append(
            s.TeamSeason(competition=m["code"], season=m["start_year"],
                         position=row.position if row else None,
                         played=row.played if row else 0, points=row.points if row else 0)
        )  # fmt: skip
    params = {"preview": preview, "team": team_id, "now": now}
    recent = _rows(
        conn,
        _FIXTURE_SELECT
        + """ where %(team)s in (f.home_team_id, f.away_team_id)
                   and f.status in ('finished', 'awarded') order by f.kickoff_utc desc limit 5""",
        params,
    )
    upcoming = _rows(conn, _FIXTURE_SELECT + """ where %(team)s in (f.home_team_id, f.away_team_id)
                     and f.status in ('scheduled', 'postponed') and f.kickoff_utc >= %(now)s
                     order by f.kickoff_utc limit 5""", params)  # fmt: skip
    return s.TeamDetail(
        team=_team(t), country=t["country"], seasons=seasons,
        recent_results=[_fixture(r) for r in recent],
        upcoming_fixtures=[_fixture(r) for r in upcoming],
    )  # fmt: skip


# ---------------------------------------------------------------------------
# Models and performance
# ---------------------------------------------------------------------------
def model_versions(conn: Conn, current: str) -> list[s.ModelVersion]:
    rows = _rows(
        conn,
        """select model_name, model_version, count(*) as runs,
                  count(*) filter (where is_published) as published_runs,
                  min(run_at) as first_run_at, max(run_at) as last_run_at
             from model_runs group by model_name, model_version order by max(run_at) desc""",
    )
    return [s.ModelVersion(**r, is_current=r["model_version"] == current) for r in rows]


def performance(conn: Conn, current: str) -> s.PerformanceResponse:
    def latest(kind: str) -> s.BacktestOut | None:
        r = _one(
            conn,
            """select id, kind, model_version, run_at, tuning_window, test_window, params, metrics
                 from backtest_runs where kind = %s order by run_at desc, id desc limit 1""",
            (kind,),
        )
        if r is None:
            return None
        return s.BacktestOut(backtest_id=r.pop("id"), **r)

    return s.PerformanceResponse(
        current_model_version=current, match_level=latest("match"), season_level=latest("season")
    )
