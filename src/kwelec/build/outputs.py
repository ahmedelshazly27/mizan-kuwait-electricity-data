"""Downloads (data/out/) and the page's data (data/web/) from the extracted observations.

data/out/ holds the tidy observations with full provenance, the lookup tables, the
validation results and the conflict register, as CSV and Parquet, described by a
Frictionless datapackage.json. data/web/ holds compact JSON for the page."""

import csv
import json
from collections import defaultdict
from decimal import Decimal as D
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import yaml

REPO = "ahmedelshazly27/mizan-kuwait-electricity-data"
SOURCES_RELEASE = "sources-2026-10-21"


def archive_url(file: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{SOURCES_RELEASE}/{file}"


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in fields} for r in rows)


def _tables(config: Path, sources: list[dict]) -> list[dict]:
    out = []
    for s in sources:
        ed = config / "editions" / f"{s['id']}.yaml"
        if not ed.exists():
            out.append({"source_id": s["id"], "table_no": "EDATA", "title_en": s["title_en"], "title_ar": None,
                        "unit_printed": None, "sheet": None, "pages_pdf": None})
            continue
        for t in yaml.safe_load(ed.read_text())["tables"]:
            pages = t.get("page_pdf")
            out.append({"source_id": s["id"], "table_no": t.get("table_no") or t["id"], "title_en": t.get("title_en"),
                        "title_ar": t.get("title_ar"), "unit_printed": t.get("unit_printed"), "sheet": t.get("sheet"),
                        "pages_pdf": json.dumps(pages if isinstance(pages, list) else [pages]) if pages else None})
    return out


def build(obs_csv: Path, out: Path, web: Path, config: Path, registry: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    obs = list(csv.DictReader(obs_csv.open()))
    sources = yaml.safe_load((config / "sources.yaml").read_text())["sources"]
    reg = {n: yaml.safe_load((registry / f"{n}.yaml").read_text()) for n in ("plants", "sectors", "variables", "units", "fuels")}
    review = yaml.safe_load((config / "conflicts.yaml").read_text())

    # Lookup tables.
    src_rows = [{**{k: s.get(k) for k in ("id", "publisher", "series", "tier", "title_en", "title_ar", "data_year",
                                           "data_month", "cover_year_printed", "issued_printed", "year_convention",
                                           "retrieved_at", "sha256", "licence_note", "note")},
                 "url": s["fetch"].get("url") or {"csb_postback": "https://www.csb.gov.kw/Pages/Statistics?ID=44&ParentCatID=4",
                                                  "undata": "https://data.un.org/Data.aspx?d=EDATA&f=cmID:EL;crID:414"}[s["fetch"]["method"]],
                 "archive_url": archive_url(s["file"]) if s["tier"] == "primary" else None} for s in sources]
    _write(out / "sources.csv", src_rows, list(src_rows[0]))
    tables = _tables(config, sources)
    _write(out / "source_tables.csv", tables, list(tables[0]))
    labels = defaultdict(set)
    for o in obs:
        labels[o["source_id"]].update(x.strip(" *").lower() for x in (o["col_label"] + " / " + o["row_label"]).split(" / "))
    plants, aliases = [], []
    for p in reg["plants"]["plants"]:
        plants.append({"id": p["id"], "kind": p["kind"], "parent": p.get("parent"), "name_en": p["name_en"],
                       "name_ar": p["name_ar"], "name_ar_reviewed": "false"})
        for a in p["aliases"]:
            seen = sorted(sid for sid, ls in labels.items() if a.strip(" *").lower() in ls)
            aliases.append({"alias": a, "plant_id": p["id"], "seen_in": json.dumps(seen)})
    _write(out / "plants.csv", plants, list(plants[0]))
    _write(out / "plant_aliases.csv", aliases, list(aliases[0]))
    sectors = [{"id": s["id"], "parent": s.get("parent"), "en": s["en"], "ar": s.get("ar"), "un_label": s.get("un")}
               for s in reg["sectors"]["sectors"]]
    _write(out / "sectors.csv", sectors, list(sectors[0]))
    variables = [{"id": k, "unit": v.get("unit"), "en": v["en"], "ar": v.get("ar")} for k, v in reg["variables"]["variables"].items()]
    _write(out / "variables.csv", variables, list(variables[0]))
    units = [{"printed": k, "canonical": v["canonical"], "factor": v.get("factor"), "note": v.get("note")}
             for k, v in reg["units"]["units"].items()]
    _write(out / "units.csv", units, list(units[0]))
    fuels = [{"id": k, "en": v["en"], "ar": v.get("ar")} for k, v in reg["fuels"]["fuels"].items()]
    _write(out / "fuels.csv", fuels, list(fuels[0]))

    # Observations, with the canonical value next to the printed one.
    unit = {u["printed"]: u for u in units}
    fields = list(obs[0]) + ["canonical_value", "canonical_unit"]
    for o in obs:
        u = unit[o["unit_printed"]]
        o["canonical_value"] = str(D(o["value"]) * D(str(u["factor"]))) if o["value"] and u["factor"] is not None else ""
        o["canonical_unit"] = u["canonical"]
    _write(out / "observations.csv", obs, fields)

    # Conflicts with the owner's review status.
    status = {c["id"]: c for c in review["conflicts"]}
    conf = list(csv.DictReader((out / "conflicts.csv").open()))
    for c in conf:
        r = status[c["id"]]
        c.update({"group": r["group"], "group_note": review["groups"][r["group"]], "status": r["status"],
                  "decision": r.get("decision"), "decided_by": r.get("decided_by"), "decided_at": r.get("decided_at")})
    _write(out / "conflicts.csv", conf, ["id", "group", "kind", "key", "canonical_values", "unit", "spread", "status",
                                         "decision", "decided_by", "decided_at", "members", "values", "group_note", "note"])

    # Parquet copies.
    for name in ("observations", "sources", "plants", "sectors", "variables", "units", "conflicts", "validation"):
        t = pacsv.read_csv(out / f"{name}.csv", convert_options=pacsv.ConvertOptions(strings_can_be_null=True,
                           column_types={"value": pa.string(), "canonical_value": pa.string()} if name == "observations" else None))
        pq.write_table(t, out / f"{name}.parquet", compression="zstd")

    _datapackage(out, obs, sources)
    _web(web, obs, conf, out, sources, reg)
    print(f"{len(obs)} observations, {len(conf)} conflicts -> {out}, page data -> {web}")
    return 0


def _datapackage(out: Path, obs: list[dict], sources: list[dict]) -> None:
    res = []
    for f in sorted(out.glob("*.csv")):
        with f.open() as fh:
            header = next(csv.reader(fh))
        res.append({"name": f.stem.replace("_", "-"), "path": f.name, "format": "csv", "mediatype": "text/csv",
                    "encoding": "utf-8", "schema": {"fields": [{"name": h, "type": "string"} for h in header]}})
    pkg = {
        "name": "kuwait-electricity-open-dataset",
        "title": "Kuwait Electricity Open Dataset",
        "description": ("Every electricity value printed in the primary statistical publications of Kuwait's Ministry of "
                        "Electricity, Water and Renewable Energy (MEW) and Central Statistical Bureau (CSB) that the "
                        "pipeline extracts, one row per printed cell with its provenance; UNdata consumption by sector "
                        "as a separate secondary table. Missing values stay missing; disagreements are recorded, not resolved."),
        "homepage": "https://mizan-energy.com/research/kuwait-electricity-data/",
        "licenses": [{"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/",
                      "title": "Creative Commons Attribution 4.0 (the compilation; see sources.csv for each publisher's terms)"}],
        "sources": [{"title": s["title_en"], "path": s["fetch"].get("url", "")} for s in sources],
        "resources": res,
    }
    (out / "datapackage.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False))


def _web(web: Path, obs: list[dict], conf: list[dict], out: Path, sources: list[dict], reg: dict) -> None:
    """Compact series for the page. Values are the newest edition's within each series;
    every point carries its source id so the page can cite it."""
    in_conflict = {m for c in conf for m in c["members"].split()}
    newest = {}
    order = {s["id"]: (s.get("data_year") or 0, s.get("data_month") or 0) for s in sources}
    for o in obs:
        if o["source_id"].startswith("undata"):
            continue
        k = (o["source_id"].rsplit("-", 1)[0] if not o["source_id"].startswith("mew-mb") else "mew-mb",
             o["table_no"] if o["source_id"].startswith("mew") else o["variable"],
             o["variable"], o["level"], o["plant_id"], o["unit_group"], o["period_start"], o["period_end"], o["frequency"])
        if k not in newest or order[o["source_id"]] > order[newest[k]["source_id"]]:
            newest[k] = o

    def pts(pred):
        rows = [o for o in newest.values() if pred(o)]
        return sorted(({"p": o["period_start"][:7] if o["frequency"] != "annual" else o["period_start"][:4],
                        "v": float(o["canonical_value"]) if o["canonical_value"] else None, "s": o["source_id"],
                        "x": o["value_printed"], "c": o["id"] in in_conflict, "id": int(o["id"])} for o in rows),
                      key=lambda d: d["p"])

    plants = [p["id"] for p in reg["plants"]["plants"] if p["kind"] in ("power_station", "renewable")]
    data = {
        "generation_annual_mew": pts(lambda o: o["table_no"] == "generation-history" and o["level"] == "national"),
        "generation_annual_mew_by_plant": {p: pts(lambda o, p=p: o["table_no"] == "generation-history" and o["plant_id"] == p) for p in plants},
        "generation_annual_csb": pts(lambda o: o["source_id"].startswith("csb") and o["variable"] == "generation_gross"
                                     and o["level"] == "national" and o["frequency"] == "annual"),
        "generation_monthly_csb": pts(lambda o: o["source_id"].startswith("csb") and o["variable"] == "generation_gross"
                                      and o["level"] == "national" and o["frequency"] == "monthly"),
        "generation_monthly_csb_by_plant": {p: pts(lambda o, p=p: o["source_id"].startswith("csb") and o["variable"] == "generation_gross"
                                                   and o["plant_id"] == p and o["frequency"] == "monthly") for p in plants},
        "capacity_annual_mew": pts(lambda o: o["table_no"] == "capacity-history" and o["level"] == "national"),
        "capacity_annual_mew_by_plant": {p: pts(lambda o, p=p: o["table_no"] == "capacity-history" and o["plant_id"] == p) for p in plants},
        "peak_load_mew": pts(lambda o: o["table_no"] == "peak-history" and o["variable"] == "peak_load"),
        "min_load_mew": pts(lambda o: o["table_no"] == "load-history" and o["variable"] == "min_load"),
        "temperature_at_peak_mew": pts(lambda o: o["table_no"] == "peak-history" and o["variable"] == "temperature_at_peak"),
        "peak_date_mew": pts(lambda o: o["table_no"] == "peak-history" and o["variable"] == "peak_load_date"),
        "station_use_annual_mew": pts(lambda o: o["table_no"] == "energy-history" and o["variable"] == "station_use"),
        "sent_out_net_annual_mew": pts(lambda o: o["table_no"] == "energy-history" and o["variable"] == "sent_out_net_total"),
        "generation_daily_2025": pts(lambda o: o["source_id"].startswith("mew-mb") and o["table_no"] == "generation-daily"
                                     and o["level"] == "national" and o["frequency"] == "daily"),
    }
    un = defaultdict(list)
    for o in obs:
        if o["variable"] == "consumption":
            un[o["sector_id"]].append({"p": o["period_start"][:4], "v": float(o["canonical_value"]) if o["canonical_value"] else None,
                                       "x": o["value_printed"], "est": bool(o["footnote_printed"]), "id": int(o["id"])})
    data["consumption_secondary_un"] = {k: sorted(v, key=lambda d: d["p"]) for k, v in un.items()}
    un_gross = {o["period_start"][:4]: float(o["canonical_value"]) for o in obs if o["variable"] == "un_gross_production" and o["canonical_value"]}
    data["crosscheck_un_vs_mew"] = [{"p": d["p"], "mew": d["v"], "un": un_gross.get(d["p"])}
                                    for d in data["generation_annual_mew"] if d["p"] in un_gross]

    # Coverage matrix: variable x year, which series print it.
    cov = defaultdict(lambda: defaultdict(set))
    for o in obs:
        if o["value_status"] == "number":
            fam = ("UNdata (secondary)" if o["source_id"].startswith("undata") else "MEW monthly books" if o["source_id"].startswith("mew-mb")
                   else "MEW yearbooks" if o["source_id"].startswith("mew") else "CSB workbooks")
            for y in range(int(o["period_start"][:4]), int(o["period_end"][:4]) + 1):
                cov[o["variable"] + (":" + o["level"] if o["level"] in ("plant", "sector") else "")][y].add(fam)
    data["coverage"] = {k: {str(y): sorted(v) for y, v in sorted(ys.items())} for k, ys in cov.items()}

    val = list(csv.DictReader((out / "validation.csv").open()))
    summ = defaultdict(lambda: defaultdict(int))
    for r in val:
        summ[r["check"]][r["status"]] += 1
    data["validation"] = {k: dict(v) for k, v in summ.items()}
    data["conflicts"] = [{k: c[k] for k in ("id", "group", "kind", "key", "canonical_values", "unit", "status", "values")} for c in conf]
    data["sources"] = [{"id": s["id"], "publisher": s["publisher"], "title_en": s["title_en"], "title_ar": s.get("title_ar"),
                        "tier": s["tier"], "data_year": s.get("data_year"), "cover_year_printed": s.get("cover_year_printed"),
                        "issued_printed": s.get("issued_printed"), "sha256": s["sha256"],
                        "archive_url": archive_url(s["file"]) if s["tier"] == "primary" else None,
                        "url": s["fetch"].get("url")} for s in sources]
    data["plants"] = reg["plants"]["plants"]
    data["counts"] = {"observations": len(obs), "sources": len(sources),
                      "numbers": sum(o["value_status"] == "number" for o in obs)}
    (web / "electricity.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
