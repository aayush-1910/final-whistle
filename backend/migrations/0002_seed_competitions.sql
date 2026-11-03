-- ============================================================================
-- 0002 — The five V1 competitions and their football-data.org codes.
-- Codes verified against real API responses on 2026-11-03
-- (docs/milestone-0-football-data-org-report.md).
-- ============================================================================

insert into competitions (code, name, format, country) values
    ('EPL',        'Premier League',        'domestic_league',  'England'),
    ('LA_LIGA',    'La Liga',               'domestic_league',  'Spain'),
    ('BUNDESLIGA', 'Bundesliga',            'domestic_league',  'Germany'),
    ('SERIE_A',    'Serie A',               'domestic_league',  'Italy'),
    ('UCL',        'UEFA Champions League', 'champions_league', null);

insert into competition_provider_ids (competition_id, provider, external_id)
select c.id, 'football_data_org', v.ext
from (values
    ('EPL', 'PL'), ('LA_LIGA', 'PD'), ('BUNDESLIGA', 'BL1'), ('SERIE_A', 'SA'), ('UCL', 'CL')
) as v (code, ext)
join competitions c on c.code = v.code;
