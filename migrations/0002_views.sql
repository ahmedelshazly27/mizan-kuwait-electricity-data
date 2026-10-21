-- Views. Units are normalised here only (canonical_value); the tables keep every
-- value as printed. All views run with the caller's rights, so RLS applies.

create view public.obs_canonical with (security_invoker = true) as
select o.*,
       s.publisher, s.series, s.tier, s.data_year as edition_year, s.data_month as edition_month,
       u.canonical as canonical_unit,
       o.value * u.factor as canonical_value,
       exists (select 1 from public.conflict_members m join public.conflicts c on c.id = m.conflict_id
               where m.observation_id = o.id and c.status = 'open') as in_open_conflict
from public.observations o
join public.sources s on s.id = o.source_id
join public.units u on u.printed = o.unit_printed;

-- The newest edition's value for each quantity, within each series (MEW yearbooks,
-- MEW monthly books, CSB workbooks and UNdata stay separate). Where an open conflict
-- touches a value, `in_open_conflict` says so; no value is chosen over another.
create view public.latest with (security_invoker = true) as
select distinct on (series, variable, level, plant_id, sector_id, fuel, unit_group, period_start, period_end, frequency)
       *
from public.obs_canonical
order by series, variable, level, plant_id, sector_id, fuel, unit_group, period_start, period_end, frequency,
         edition_year desc, edition_month desc nulls last, id;

-- Quantities printed in more than one edition of a series with different values.
create view public.revisions with (security_invoker = true) as
select series, variable, level, plant_id, sector_id, fuel, unit_group, period_start, period_end, frequency,
       canonical_unit,
       jsonb_agg(jsonb_build_object('source_id', source_id, 'value_printed', value_printed,
                                    'canonical_value', canonical_value, 'table_no', table_no, 'page_pdf', page_pdf)
                 order by edition_year) as editions
from public.obs_canonical
where value_status = 'number'
group by series, variable, level, plant_id, sector_id, fuel, unit_group, period_start, period_end, frequency, canonical_unit
having count(distinct source_id) > 1 and max(canonical_value) <> min(canonical_value);

create view public.generation with (security_invoker = true) as
select series, source_id, level, plant_id, period_start, period_end, frequency,
       canonical_value as mwh, value_printed, unit_printed, value_status, table_no, page_pdf, sheet, cell_ref, in_open_conflict
from public.latest
where variable = 'generation_gross' and tier = 'primary';

create view public.capacity with (security_invoker = true) as
select series, source_id, level, plant_id, period_start, period_end,
       canonical_value as mw, value_printed, value_status, table_no, page_pdf, sheet, cell_ref, in_open_conflict
from public.latest
where variable = 'installed_capacity' and tier = 'primary';

create view public.peak_load with (security_invoker = true) as
select l.series, l.source_id, l.period_start, l.canonical_value as mw, l.value_printed,
       d.value_printed as date_printed, t.canonical_value as temperature_c, h.canonical_value as humidity_pct,
       l.table_no, l.page_pdf, l.in_open_conflict
from public.latest l
left join public.latest d on d.series = l.series and d.period_start = l.period_start and d.variable = 'peak_load_date'
left join public.latest t on t.series = l.series and t.period_start = l.period_start and t.variable = 'temperature_at_peak'
left join public.latest h on h.series = l.series and h.period_start = l.period_start and h.variable = 'humidity_at_peak'
where l.variable = 'peak_load';

-- UNdata's consumption by sector: a secondary source, kept apart. footnote "1 - Estimate"
-- marks UN estimates.
create view public.consumption_secondary with (security_invoker = true) as
select o.sector_id, s.en as sector_en, s.ar as sector_ar, s.parent as part_of,
       o.period_start, o.canonical_value as mwh, o.value_printed, o.unit_printed, o.footnote_printed,
       o.source_id
from public.obs_canonical o
join public.sectors s on s.id = o.sector_id
where o.variable = 'consumption' and o.tier = 'secondary';

-- What exists: per variable, entity and series, the years covered and how many
-- cells were printed as numbers, dashes or blanks.
create view public.coverage with (security_invoker = true) as
select variable, level, coalesce(plant_id, sector_id, 'national') as entity, series, tier, frequency,
       min(extract(year from period_start))::int as first_year,
       max(extract(year from period_end))::int as last_year,
       count(distinct source_id) as editions,
       count(*) filter (where value_status = 'number') as numbers,
       count(*) filter (where value_status = 'dash') as dashes,
       count(*) filter (where value_status = 'blank') as blanks,
       count(*) filter (where value_status = 'text') as texts
from public.obs_canonical
group by variable, level, coalesce(plant_id, sector_id, 'national'), series, tier, frequency;

-- The secondary national series against MEW's: reported, never merged.
create view public.crosscheck with (security_invoker = true) as
select u.period_start, u.canonical_value as un_gross_mwh, m.canonical_value as mew_generation_mwh,
       u.canonical_value - m.canonical_value as difference_mwh,
       round((u.canonical_value - m.canonical_value) / nullif(m.canonical_value, 0) * 100, 2) as difference_pct,
       u.footnote_printed as un_footnote, m.source_id as mew_source, m.table_no as mew_table
from public.latest u
join public.latest m on m.period_start = u.period_start and m.variable = 'generation_gross' and m.level = 'national'
                     and m.frequency = 'annual' and m.series = 'Statistical Year Book – Electrical Energy'
                     and m.table_no = 'generation-history'
where u.variable = 'un_gross_production';
