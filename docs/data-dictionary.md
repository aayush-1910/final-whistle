# Data Dictionary

> Canonical domain contracts for Final Whistle. Source: `backend/app/domain/models.py`.
> The database schema (Milestone 2) will be derived from these. Every class
> validates itself on construction and raises `DomainValidationError` on bad data.

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
| `stage` | `Stage` | `regular_season`, `league_stage`, `playoffs`, `last_16`, `quarter_finals`, `semi_finals`, `final`, `other` |
| `matchday` | int \| None | ≥ 1 |
| `home_score`, `away_score` | int \| None | Both or neither; non-negative |
| `provider_status` | str \| None | Original provider status, kept for audit |
| `provider_ref` | ProviderRef \| None | |

**Status rules**

| Status | Score allowed | Score required | Counts in table (`is_completed`) | Simulated (`is_to_be_played`) |
|---|---|---|---|---|
| `scheduled` | no | no | no | **yes** |
| `postponed` | no | no | no | **yes** |
| `in_progress` | yes | no | no | no |
| `suspended` | yes | no | no | no |
| `abandoned` | yes | no | no | no |
| `finished` | yes | **yes** | **yes** | no |
| `awarded` | yes | **yes** | **yes** | no |
| `cancelled` | no | no | no | no |
| `unknown` | yes | no | no | no; must be investigated |

Open question for Milestone 4: how a forecast run should treat `in_progress` and `suspended` fixtures. Currently neither is simulated nor counted.

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
