# Kuwait Electricity Open Dataset

Every electricity number we could extract from Kuwait's primary statistical
publications, one row per printed cell, each with the document, table, page or
cell it came from. Missing values stay missing. Where two documents print different
numbers for the same thing, both are kept and the disagreement is listed. Nothing
is estimated, interpolated, averaged or filled.

Page: <https://mizan-energy.com/research/kuwait-electricity-data/> ·
Code: MIT ([LICENSE](LICENSE)) · Data: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)) ·
Cite: [CITATION.cff](CITATION.cff)

## What is in it

| Source (primary unless marked) | Editions | What we extract | Cells |
|---|---|---|---|
| MEW Statistical Year Book, Electrical Energy | data years 2020, 2021, 2022, 2023 | every generating unit with its block, technology, date of commissioning (as printed) and rating, from the station pages (114–117 units per edition, each station summing to its printed total); 1991/92/93/94–data-year history of installed capacity and generation by station, generation / station use / net sent out, maximum and minimum load, system peak with date, temperature and humidity; monthly generation, station use and net export by station for the data year | 6,659 |
| MEW Monthly Statistics Book | May, June, July 2025 | daily generation and export by station, desalination use, net export | 2,375 |
| CSB Environment Statistics, electricity chapter (.xlsx) | 2013–2024 | monthly generation, station use and sent out by station; monthly fuel use by station (gas, gas oil, crude, heavy oil); plant capacity and first operating year (2019–2024) | 11,457 |
| UNdata Energy Statistics (**secondary**) | retrieved 2026-10-21 | consumption by sector 1990s–2023 (no primary source publishes this); supply rows used only for cross-checks | 503 |

20,994 cells: 19,258 numbers, 649 printed dashes, 144 printed non-numbers
(composites such as `804+25`, dates), 25 blanks (nothing printed in a column that
exists). See `coverage` in the database, or the coverage table on the page.

**Not in it, because no source has it:** electricity consumption by governorate
(MEW's "governorate" tables count new connections and connected load, a different
variable), any primary consumption by sector, MEW yearbooks for 2017–2019 (listed on
mew.gov.kw with no files) and for 2024. **Not yet extracted** (v1 scope): MEW unit-level
tables (availability, running hours), fuel and fuel-cost tables, available capacity
at 31 December, CSB fuel cost and revenue, the CSB Statistical Abstract vintages,
EIA and IRENA cross-checks, and the Arab Union of Electricity peak-load check.

## How values are kept

- `value_printed` is the cell exactly as printed (for workbooks, as displayed by its
  number format); `value` is the number it states, or null when the cell is a dash,
  blank or not a plain number. A dash is never read as zero.
- For workbooks, `value` is the number stored in the cell (to the 15 significant digits
  a spreadsheet keeps), which can carry more decimals than are displayed; formula
  cells keep their formula in `cell_formula` (e.g. CSB 2016's monthly sent-out totals
  are `=SUM(D8:M8)-586`, an unexplained adjustment in the workbook itself).
- Units stay as printed (`Million kWh`, `MW/H`, `Million WH`, `T.C.F` …);
  `canonical_value` converts with exact definitional factors from
  [registry/units.yaml](registry/units.yaml) (MWh, MW, thousand cubic feet, barrels).
- Each edition's values are kept separately, so restatements between editions are
  visible (`revisions` view).
- Cover year and data year are separate: the 2023 book's cover says "2023", its issue
  line says "2024".

## Disagreements

`kwelec validate` runs every check it can (months add up to totals, stations to the
national figure, net export to export minus desalination use, editions against each
other, CSB against MEW, the peak load against the year's maximum load) and writes
`data/out/validation.csv`. Printed values that disagree beyond rounding become
**conflicts**, listed in [config/conflicts.yaml](config/conflicts.yaml) with status
`open` until the owner decides. A conflict that appears without being listed there
fails the run. The current 33 fall into four groups:

- **A (4)**: the MEW 2021 edition's capacity table prints its Total column shifted
  by a year in some rows (e.g. 18,793 MW for 2019, which is 2018's total).
- **B (8)**: CSB's plant capacities for 2020–2022 repeat older figures than MEW's.
- **C (20)**: CSB workbook totals and MEW yearbook history differ slightly
  (mostly under 0.3%) for the same plant-year.
- **D (1)**: MEW 2020 prints national generation for 2020 as 74,756.3 and 74,757.

Other findings, not conflicts: CSB 2016's monthly sent-out totals subtract
unexplained constants, so its months do not add to its printed annual total; the MEW
2023 book prints the 2023 peak date as `08/02/2023` while its peak-day chart is titled
2 August 2023; MEW 2020 prints some peak dates month-first (`6/27/2019`). Dates
are therefore kept as printed and never parsed.

## Rebuild

Requires [uv](https://docs.astral.sh/uv/) and `pdftotext` (poppler-utils).

```sh
make            # fetch -> extract -> validate -> build
make test
```

- `kwelec fetch` downloads each source in [config/sources.yaml](config/sources.yaml)
  and checks it against the recorded SHA-256. mew.gov.kw needs legacy TLS
  renegotiation; [config/openssl-mew.cnf](config/openssl-mew.cnf) enables it for
  that download only, and certificate checks stay on. CSB files come through the
  site's ASP.NET postbacks, found by year on every run.
- `kwelec extract` reads each source with its reviewed edition config in
  [config/editions/](config/editions/). Column identity comes from those configs,
  checked by hand against the pages, never from the printed headers (which are
  misaligned in places, and in one MEW table mislabel Az-Zour North as Az-Zour
  South). The extractor stops if a title, header or row count no longer matches.
- `kwelec build` writes `data/out/` (CSV and Parquet, `datapackage.json`) and
  `data/web/electricity.json` for the page.
- `kwelec load` replaces the data in the Supabase project (`SUPABASE_PROJECT_REF`,
  `SUPABASE_ACCESS_TOKEN`) through the Management API, applying any new file in
  [migrations/](migrations/). The API is read-only for clients: row-level security
  allows `select` to `anon` and nothing else.

Raw files and outputs are not committed. The source documents are archived,
unmodified and with their SHA-256, as assets of the
[`sources-2026-10-21` release](https://github.com/ahmedelshazly27/mizan-kuwait-electricity-data/releases/tag/sources-2026-10-21);
they belong to their publishers (see [SOURCES.md](SOURCES.md)).

## Database

Tables: `sources`, `source_tables`, `observations`, `plants`, `plant_aliases`,
`sectors`, `variables`, `units`, `fuels`, `conflicts`, `conflict_members`,
`validation_results`, `builds`. Views: `obs_canonical`, `latest` (newest edition
per quantity within each series), `revisions`, `generation`, `capacity`,
`peak_load`, `consumption_secondary`, `coverage`, `crosscheck`.

## Layout

```
config/sources.yaml        every document: URL, SHA-256, cover and data year, licence note
config/editions/*.yaml     per-edition table maps, reviewed by hand
config/conflicts.yaml      disagreements and the owner's decisions
registry/*.yaml            plants and every spelling seen, sectors, variables, units, fuels
src/kwelec/                fetch, extract, validate, build, load
migrations/*.sql           database schema, views and access rules
tests/                     unit tests, config consistency, values checked by hand
```

Arabic plant names in [registry/plants.yaml](registry/plants.yaml) are copied from
the CSB workbooks (MEW's PDFs use a legacy Arabic font whose text layer is unusable)
and await a review by hand (`name_ar_reviewed: false`).
