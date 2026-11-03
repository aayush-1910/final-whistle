# Data Dictionary

> Canonical domain contracts for Final Whistle. Source: `backend/app/domain/models.py`.
> Every class validates itself on construction and raises `DomainValidationError` on bad data.
> The database schema mirrors these: `backend/migrations/0001_initial_schema.sql`.

## Conventions

- Internal IDs (`id`) are assigned by the database; `None` before persistence.
- Teams are referenced by canonical internal ID, never by name.
- Provider IDs live in `ProviderRef(provider, external_id)`. `external_id` is a string because providers disagree on ID types.
- All datetimes must be timezone-aware and are normalized to UTC. Naive datetimes are rejected.
- Scores: `None` means "no score" and is distinct from `0`.
- All entities are immutable (frozen dataclasses).

## Entities

### Competition
| Field | Type | Notes |
|---|---|---|
| `code` | str | Internal code: `EPL`, `LA_LIGA`, `BUNDESLIGA`, `SERIE_A`, `UCL` |
| `name` | str | |
| `format` | `CompetitionFormat` | `domestic_league` or `champions_league` |
| `country` | str \| None | `None` for continental competitions |

### Season
| Field | Type | Notes |
|---|---|---|
| `competition_code` | str | |
| `start_year` | int | `2026` means 2026/27 (matches football-data.org's `season` param) |
| `start_date`, `end_date` | date \| None | End date must not precede start date |
| `label` (derived) | str | e.g. `"2026/27"` |

### Team
| Field | Type | Notes |
|---|---|---|
| `name` | str | Required |
| `short_name`, `tla`, `country` | str \| None | |
| `provider_refs` | tuple[ProviderRef] | At most one per provider |

### Fixture
| Field | Type | Notes |
|---|---|---|
| `season_id` | int \| None | |
| `home_team_id`, `away_team_id` | int | Must differ |
| `kickoff_utc` | datetime \| None | Aware → UTC; `None` = kickoff time not yet known |
| `status` | `FixtureStatus` | See below |
| `stage` | `Stage` | `regular_season`, `league_stage`, `group_stage` (pre-2024/25 UCL), `playoffs`, `last_16`, `quarter_finals`, `semi_finals`, `final`, `other` |
| `group` | str \| None | e.g. `GROUP_A` (pre-2024/25 UCL) |
| `matchday` | int \| None | ≥ 1; `None` for a single-match final |
| `home_score`, `away_score` | int \| None | Goals in play **including extra time, excluding any shootout**. Both or neither; non-negative |
| `duration` | `MatchDuration` | `regular`, `extra_time`, `penalty_shootout` |
| `home_score_90`, `away_score_90` | int \| None | Score after 90 minutes; set only when the match went beyond 90. Read via `score_90` |
| `home_penalties`, `away_penalties` | int \| None | Shootout score; only with `penalty_shootout`. A second leg's own score need not be level (the shootout settles the aggregate) |
| `provider_status` | str \| None | Original provider status, kept for audit |
| `provider_ref` | ProviderRef \| None | |

**Status rules**

| Status | Score allowed | Score required | Counts in table (`is_completed`) | Simulated (`is_to_be_played`) |
|---|---|---|---|---|
| `scheduled` | no | no | no | **yes** |
| `postponed` | no | no | no | **yes** |
| `in_progress` | yes | no | no | **yes**: partial score ignored |
| `suspended` | yes | no | no | no |
| `abandoned` | yes | no | no | no |
| `finished` | yes | **yes** | **yes** | no |
| `awarded` | yes | **yes** | **yes** | no |
| `cancelled` | no | no | no | no |
| `unknown` | yes | no | no | no; must be investigated |

Decision (2026-11-03): an `in_progress` (live) match is treated as unplayed. It is simulated from 0-0 and its partial score does not count in the table. `suspended` fixtures are neither simulated nor counted; this will be revisited if one occurs.

### StandingRow
Provider-reported table row, used to cross-check tables we compute ourselves.
`won + drawn + lost` must equal `played`. `goal_difference` is derived.

## Season rules

`LeagueRules` defines the *shape* of season-specific competition rules: team count, points per result,
ordered `Tiebreaker` list (must start with `points`), and named position `Zone`s (e.g. `relegation` 18–20).
`is_verified` is true only when `source` and `verified_on` are set. **Unverified rules must not
drive published forecasts.** Actual 2026/27 values will be added as configuration in Milestones 4–5,
verified against official competition regulations.

## Provider status mapping (football-data.org)

| Provider | Canonical |
|---|---|
| `SCHEDULED`, `TIMED` | `scheduled` |
| `IN_PLAY`, `PAUSED` | `in_progress` |
| `FINISHED` | `finished` |
| `SUSPENDED` | `suspended` |
| `POSTPONED` | `postponed` |
| `CANCELLED` | `cancelled` |
| `AWARDED` | `awarded` |
| anything else | `unknown` (logged) |

## Derived fixture properties

| Property | Meaning |
|---|---|
| `score_90` | Score after regular time; the input for goal models |
| `outcome_90` | home / draw / away after 90 minutes; used for league tables and 1X2 forecasts |
| `winner_team_id` | More goals in this match incl. extra time; `None` if level. Ignores penalties |
| `shootout_winner_team_id` | Winner of the shootout, if there was one |

## Database tables (migration 0001)

| Table | Purpose |
|---|---|
| `competitions`, `competition_provider_ids` | The 5 competitions (seeded by 0002) and provider codes |
| `seasons` | One row per competition-season; unique `(competition_id, start_year)` |
| `teams`, `team_provider_ids` | Canonical teams; one provider ID per provider, shared across competitions (e.g. Arsenal in EPL and UCL is one team) |
| `season_teams` | Participants of each season |
| `fixtures` | Matches; unique `(provider, provider_fixture_id)`; DB-level checks mirror the domain rules |
| `standings_snapshots`, `standings_rows` | Provider tables captured on each ingestion, for cross-checking |
| `ingestion_runs` | Audit trail: status, request count, inserted/updated counts, issues, consistency result, error |
| `schema_migrations` | Applied migrations with checksums |
| `model_runs` (0003) | One forecast run: model, params, rules, data cutoff, seed, simulation count, git commit, `is_published` (default false) |
| `season_forecasts` (0003) | Per run and team: current/expected points, expected position, `position_probs` array (index 1 = 1st), `zone_probs` JSON |
| `season_forecasts.round_probs` (0004) | UCL only: probability of reaching the round of 16, quarter-finals, semi-finals, final, and of winning (`winner`) |
| `match_forecasts` (0003) | Per run and remaining fixture: home/draw/away probabilities (DB-checked to sum to 1) and expected goals |

Row-level security is enabled on every table with no policies, so Supabase's public REST roles
cannot read or write them. The backend connects as the table owner.
