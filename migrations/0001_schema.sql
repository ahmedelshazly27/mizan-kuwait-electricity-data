-- Kuwait Electricity Open Dataset: tables.
-- Every published value is one printed cell with its provenance. A value that was
-- not printed as a plain number (a dash, a blank, "804+25", a date) is stored as
-- NULL with the printed string kept; nothing is estimated or filled.

-- The loader first creates schema `pipeline` (not exposed through the API) with
-- pipeline.migrations, which records the files applied.

create table public.builds (
  id          text primary key,              -- git commit of the pipeline that built the data
  built_at    timestamptz not null,
  observations integer not null,
  note        text
);

create table public.sources (
  id                 text primary key,
  publisher          text not null,
  series             text not null,
  tier               text not null check (tier in ('primary', 'secondary')),
  title_en           text not null,
  title_ar           text,
  data_year          integer,
  data_month         integer check (data_month between 1 and 12),
  cover_year_printed text,                    -- the year as printed on the cover, kept apart from the data year
  issued_printed     text,                    -- the issue year printed on the cover, when legible
  year_convention    text not null check (year_convention in ('calendar', 'fiscal_apr_mar')),
  url                text,
  retrieved_at       date not null,
  sha256             char(64) not null,
  archive_url        text,
  licence_note       text not null,
  note               text
);

create table public.source_tables (
  source_id     text not null references public.sources (id),
  table_no      text not null,                -- printed table number, or our id where the book prints none
  title_en      text,
  title_ar      text,
  unit_printed  text,
  sheet         text,
  pages_pdf     integer[],
  primary key (source_id, table_no)
);

create table public.variables (
  id    text primary key,
  unit  text,
  en    text not null,
  ar    text
);

create table public.units (
  printed    text primary key,                -- the unit exactly as printed
  canonical  text not null,
  factor     numeric,                         -- exact, definitional factors only; null when not a quantity
  note       text
);

create table public.fuels (
  id  text primary key,
  en  text not null,
  ar  text
);

create table public.plants (
  id                text primary key,
  kind              text not null check (kind in ('power_station', 'renewable', 'ro', 'boilers')),
  parent            text references public.plants (id),
  name_en           text not null,
  name_ar           text not null,
  name_ar_reviewed  boolean not null default false
);

create table public.plant_aliases (
  alias     text not null,
  plant_id  text not null references public.plants (id),
  seen_in   text[] not null default '{}',     -- source ids where this spelling is printed
  primary key (alias, plant_id)
);

create table public.sectors (
  id        text primary key,
  parent    text references public.sectors (id),
  en        text not null,
  ar        text,
  un_label  text
);

create table public.observations (
  id                bigint primary key,
  source_id         text not null references public.sources (id),
  table_no          text not null,
  variable          text not null references public.variables (id),
  level             text not null check (level in ('national', 'plant', 'unit', 'sector')),
  plant_id          text references public.plants (id),
  sector_id         text references public.sectors (id),
  fuel              text references public.fuels (id),
  technology        text,
  unit_group        text,
  period_start      date not null,
  period_end        date not null,
  frequency         text not null check (frequency in ('annual', 'half_year', 'monthly', 'daily')),
  observed_at       timestamptz,
  value             numeric,
  value_printed     text not null,
  value_status      text not null check (value_status in ('number', 'dash', 'blank', 'text')),
  unit_printed      text not null references public.units (printed),
  row_label         text not null,
  col_label         text not null,
  method            text not null check (method in ('xlsx', 'pdf_text', 'ocr', 'manual', 'html_table')),
  page_pdf          integer,
  page_printed      text,
  sheet             text,
  cell_ref          text,
  cell_formula      text,
  ocr_confidence    real,
  footnote_printed  text,
  foreign key (source_id, table_no) references public.source_tables (source_id, table_no),
  check (period_end >= period_start),
  check ((value is not null) = (value_status = 'number')),
  check (level <> 'plant' or plant_id is not null),
  check (level <> 'sector' or sector_id is not null),
  check (level <> 'national' or (plant_id is null and sector_id is null)),
  check (method <> 'ocr' or ocr_confidence is not null),
  check (method <> 'pdf_text' or page_pdf is not null),
  check (method <> 'xlsx' or (sheet is not null and cell_ref is not null))
);

-- One row per printed cell.
create unique index observations_cell on public.observations
  (source_id, table_no, coalesce(sheet, ''), coalesce(cell_ref, ''), coalesce(page_pdf, 0),
   row_label, col_label, variable, period_start, period_end);
create index observations_key on public.observations (variable, level, plant_id, period_start);

create table public.conflicts (
  id                text primary key,
  grp               text,
  kind              text not null check (kind in ('same_edition', 'between_editions', 'between_sources')),
  key               text not null,
  canonical_values  text not null,
  unit              text,
  spread            numeric,
  status            text not null check (status in ('open', 'decided')),
  decision          text,
  decided_by        text,
  decided_at        date,
  group_note        text,
  check (status = 'open' or decision is not null)
);

create table public.conflict_members (
  conflict_id     text not null references public.conflicts (id),
  observation_id  bigint not null references public.observations (id),
  primary key (conflict_id, observation_id)
);

create table public.validation_results (
  id      bigint primary key,
  check_name text not null,
  scope   text not null,
  status  text not null check (status in ('pass', 'fail', 'not_checkable')),
  detail  text not null
);
