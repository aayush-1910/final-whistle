"""Load season-specific league rules from backend/rules/<season>/<CODE>.json."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.domain.models import LeagueRules, Tiebreaker, Zone

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


class RulesNotFoundError(FileNotFoundError):
    pass


def load_rules(
    competition_code: str, season_start_year: int, base: Path = RULES_DIR
) -> LeagueRules:
    path = base / str(season_start_year) / f"{competition_code}.json"
    if not path.is_file():
        raise RulesNotFoundError(
            f"No rules for {competition_code} {season_start_year} at {path}. "
            "Add and verify them first."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    rules = LeagueRules(
        competition_code=raw["competition_code"],
        season_start_year=raw["season_start_year"],
        team_count=raw["team_count"],
        points_for_win=raw["points_for_win"],
        points_for_draw=raw["points_for_draw"],
        tiebreakers=tuple(Tiebreaker(t) for t in raw["tiebreakers"]),
        zones=tuple(Zone(**z) for z in raw["zones"]),
        source=raw.get("source", ""),
        verified_on=date.fromisoformat(raw["verified_on"]) if raw.get("verified_on") else None,
        notes=raw.get("notes", ""),
        source_quality=raw.get("source_quality", "secondary"),
        playoff_positions=tuple(raw.get("playoff_positions", ())),
    )
    if (rules.competition_code, rules.season_start_year) != (competition_code, season_start_year):
        raise ValueError(f"{path} describes {rules.competition_code} {rules.season_start_year}")
    return rules
