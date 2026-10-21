"""Checks over the extracted observations.

Internal checks (does a printed total equal the sum of its parts?) and comparisons
(edition against edition, source against source). Nothing is corrected: a failed
check is reported, and a disagreement between two printed values becomes a conflict
with a stable id in data/out/conflicts.csv. config/conflicts.yaml records the
owner's review of each; a conflict not listed there fails the run, so a new
disagreement cannot slip through unnoticed.

Tolerance: two printed numbers agree if they differ by no more than the rounding of
the less precise one (half a unit in its last printed digit, in canonical units)."""

import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal as D
from pathlib import Path

import yaml


def _units(registry: Path) -> dict:
    return yaml.safe_load((registry / "units.yaml").read_text())["units"]


def _half_ulp(printed: str, factor: D) -> D:
    s = printed.replace(",", "").strip("* ").split()[-1] if printed else "0"
    places = len(s.split(".")[1]) if "." in s else 0
    return D(1).scaleb(-places) / 2 * factor


class Obs:
    __slots__ = ("r", "v", "tol", "unit")

    def __init__(self, r: dict, units: dict):
        self.r = r
        u = units[r["unit_printed"]]
        f = D(str(u["factor"])) if u.get("factor") is not None else None
        self.unit = u["canonical"]
        self.v = D(r["value"]) * f if (r["value"] and f is not None) else None
        self.tol = _half_ulp(r["value_printed"], f) if f is not None else D(0)

    def ref(self) -> str:
        r = self.r
        where = f"p{r['page_pdf']}" if r["page_pdf"] else (f"{r['sheet']}!{r['cell_ref']}" if r["cell_ref"] else r["row_label"])
        return f"{r['source_id']} {r['table_no']} {where} [{r['row_label']} / {r['col_label']}] = {r['value_printed']!r}"


def _sum(parts: list[Obs]) -> tuple[D, D]:
    return sum((p.v for p in parts), D(0)), sum((p.tol for p in parts), D(0))


def _agree(a: D, ta: D, b: D, tb: D) -> bool:
    return abs(a - b) <= ta + tb


def run(obs_csv: Path, out: Path, registry: Path, config: Path) -> int:
    units = _units(registry)
    rows = [Obs(r, units) for r in csv.DictReader(obs_csv.open())]
    results: list[dict] = []
    conflicts: list[dict] = []

    def result(check, scope, ok, detail):
        results.append({"check": check, "scope": scope, "status": "pass" if ok else "fail", "detail": detail})

    def conflict(kind, key, clusters: list[list[Obs]], note=""):
        refs = sorted(o.ref() for c in clusters for o in c)
        cid = hashlib.sha1(json.dumps([kind, key, refs]).encode()).hexdigest()[:10]
        vals = sorted({c[0].v for c in clusters})
        conflicts.append({"id": cid, "kind": kind, "key": key,
                          "values": " || ".join(" ; ".join(o.ref() for o in c) for c in clusters),
                          "members": " ".join(sorted((o.r["id"] for c in clusters for o in c), key=int)),
                          "canonical_values": " / ".join(str(v) for v in vals), "unit": clusters[0][0].unit,
                          "spread": str(vals[-1] - vals[0]), "note": note})

    by_table = defaultdict(list)
    for o in rows:
        by_table[(o.r["source_id"], o.r["table_no"])].append(o)

    # 1. Periods: months (or days) add up to the printed total, per column.
    for (sid, tno), obs in by_table.items():
        cols = defaultdict(lambda: {"parts": [], "half": [], "total": None})
        for o in obs:
            if o.v is None:
                continue
            k = (o.r["variable"], o.r["col_label"], o.r["cell_ref"][:1] if o.r["cell_ref"] else "")
            if o.r["frequency"] in ("monthly", "daily") and not (o.r["frequency"] == "monthly" and o.r["row_label"] == "Total"):
                cols[k]["parts"].append(o)
            elif o.r["frequency"] == "half_year":
                cols[k]["half"].append(o)
            elif o.r["frequency"] in ("annual", "monthly"):
                cols[k]["total"] = o
        for k, c in cols.items():
            if not c["parts"] or c["total"] is None:
                continue
            s, ts = _sum(c["parts"])
            t = c["total"]
            ok = _agree(s, ts, t.v, t.tol)
            result("periods_sum_to_total", f"{sid} {tno} {k[1]}", ok,
                   f"sum of {len(c['parts'])} periods {s} vs printed total {t.v} ({t.ref()})")
            for h in c["half"]:
                months = [p for p in c["parts"] if h.r["period_start"] <= p.r["period_start"] <= h.r["period_end"]]
                hs, hts = _sum(months)
                result("months_sum_to_half_year", f"{sid} {tno} {k[1]} {h.r['period_start'][:7]}",
                       _agree(hs, hts, h.v, h.tol), f"sum {hs} vs printed sub total {h.v} ({h.ref()})")

    # 2. Plants add up to the national column, per row, where the table defines it so:
    # generation (every source) and MEW's total station export.
    for (sid, tno), obs in by_table.items():
        groups = defaultdict(lambda: {"plants": [], "national": None})
        for o in obs:
            if o.r["variable"] not in ("generation_gross", "sent_out", "installed_capacity"):
                continue
            if o.v is None and o.r["value_status"] != "text":
                continue
            if o.r["variable"] == "sent_out" and sid.startswith("csb-"):
                continue  # CSB's sent-out national column is net of desalination use; checked below
            k = (o.r["variable"], o.r["period_start"], o.r["period_end"], o.r["frequency"])
            if o.r["level"] == "plant" and o.r["plant_id"] in PLANTS_IN_TOTAL:
                groups[k]["plants"].append(o)
            elif o.r["level"] == "national":
                groups[k]["national"] = o
        for k, g in groups.items():
            if g["national"] is None or not g["plants"]:
                continue
            n = g["national"]
            if n.v is None or any(p.v is None for p in g["plants"]):   # e.g. a printed "804+25"
                results.append({"check": "plants_sum_to_national", "scope": f"{sid} {tno} {k[0]} {k[1]}..{k[2]}",
                                "status": "not_checkable", "detail": "a part or the total is printed as text: "
                                + "; ".join(p.ref() for p in g["plants"] + [n] if p.v is None)})
                continue
            s, ts = _sum(g["plants"])
            result("plants_sum_to_national", f"{sid} {tno} {k[0]} {k[1]}..{k[2]}", _agree(s, ts, n.v, n.tol),
                   f"sum of {len(g['plants'])} plants {s} vs printed total {n.v} ({n.ref()})")

    # 3. Net sent out = station export minus desalination use (MEW net-export tables, CSB sent-out).
    for (sid, tno), obs in by_table.items():
        g = defaultdict(lambda: {"net": None, "parts": [], "minus": []})
        for o in obs:
            if o.v is None:
                continue
            k = (o.r["period_start"], o.r["period_end"], o.r["frequency"])
            if o.r["variable"] == "sent_out_net_total":
                g[k]["net"] = o
            elif o.r["variable"] == "desalination_use":
                g[k]["minus"].append(o)
            elif o.r["variable"] == "sent_out" and o.r["level"] == ("plant" if sid.startswith("csb-") else "national"):
                g[k]["parts"].append(o)
        for k, x in g.items():
            if x["net"] is None or not x["parts"]:   # history tables print the net figure alone
                continue
            s, ts = _sum(x["parts"])
            m, tm = _sum(x["minus"])
            for variant, val in (("minus", s - m), ("as_printed_signs", s + m)):
                if _agree(val, ts + tm, x["net"].v, x["net"].tol):
                    result("net_sent_out", f"{sid} {tno} {k[0]}..{k[1]}", True,
                           f"export {s} and desalination {m} ({variant}) give {val}; printed {x['net'].v}")
                    break
            else:
                result("net_sent_out", f"{sid} {tno} {k[0]}..{k[1]}", False,
                       f"export {s}, desalination {m}: neither {s - m} nor {s + m} equals printed {x['net'].v} ({x['net'].ref()})")

    # 4. Editions and sources: the same quantity printed in more than one place.
    def key(o: Obs):
        r = o.r
        return (r["variable"], r["level"], r["plant_id"], r["sector_id"], r["fuel"], r["unit_group"],
                r["period_start"], r["period_end"], r["frequency"],
                r["row_label"] if r["level"] == "unit" else "", r["observed_at"] if r["frequency"] == "instant" else "")

    same = defaultdict(list)
    for o in rows:
        if o.v is not None and not o.r["source_id"].startswith("undata-"):
            same[key(o)].append(o)
    for k, obs in same.items():
        if len(obs) < 2:
            continue
        # Group the printed values into clusters that agree within rounding.
        clusters: list[list[Obs]] = []
        for o in sorted(obs, key=lambda o: o.r["source_id"]):
            for c in clusters:
                if all(_agree(o.v, o.tol, x.v, x.tol) for x in c):
                    c.append(o)
                    break
            else:
                clusters.append([o])
        ids = {o.r["source_id"] for o in obs}
        series = {i.rsplit("-", 1)[0] for i in ids}
        kind = "same_edition" if len(ids) == 1 else "between_editions" if len(series) == 1 else "between_sources"
        scope = f"{k[0]} {k[2] or k[3] or 'national'} {k[6]}..{k[7]} {k[8]}"
        result(f"agree_{kind}", scope, len(clusters) == 1, " | ".join(o.ref() for o in obs))
        if len(clusters) > 1:
            conflict(kind, scope, clusters)

    # 4b. Within an edition, the system peak and the year's maximum load are one number printed twice.
    peaks = defaultdict(dict)
    for o in rows:
        if o.r["variable"] in ("peak_load", "max_load") and o.v is not None:
            peaks[(o.r["source_id"], o.r["period_start"])][o.r["variable"]] = o
    for (sid, p), d in peaks.items():
        if len(d) == 2:
            a, b = d["peak_load"], d["max_load"]
            ok = _agree(a.v, a.tol, b.v, b.tol)
            result("peak_equals_max_load", f"{sid} {p[:4]}", ok, f"{a.ref()} vs {b.ref()}")
            if not ok:
                conflict("same_edition", f"peak vs max load {p[:4]}", [[a], [b]])

    # 5. The secondary source against the primary national series (reported, never merged).
    un = {o.r["period_start"]: o for o in rows if o.r["variable"] == "un_gross_production" and o.v is not None}
    mew = {}
    for o in rows:
        if (o.r["variable"] == "generation_gross" and o.r["level"] == "national" and o.r["frequency"] == "annual"
                and o.r["source_id"].startswith("mew-yb") and o.r["table_no"] == "generation-history" and o.v is not None):
            if o.r["period_start"] not in mew or o.r["source_id"] > mew[o.r["period_start"]].r["source_id"]:
                mew[o.r["period_start"]] = o
    for p, u in sorted(un.items()):
        if p in mew:
            m = mew[p]
            result("secondary_vs_primary", f"generation {p[:4]}", _agree(u.v, u.tol, m.v, m.tol),
                   f"UNdata gross production {u.v} MWh vs MEW generation {m.v} MWh ({m.ref()}); "
                   f"difference {u.v - m.v} MWh ({(u.v - m.v) / m.v * 100:.2f}%)")

    out.mkdir(parents=True, exist_ok=True)
    with (out / "validation.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["check", "scope", "status", "detail"])
        w.writeheader()
        w.writerows(results)
    with (out / "conflicts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["id", "kind", "key", "values", "members", "canonical_values", "unit", "spread", "note"])
        w.writeheader()
        w.writerows(conflicts)

    reviewed = yaml.safe_load((config / "conflicts.yaml").read_text()) or {} if (config / "conflicts.yaml").exists() else {}
    known = {c["id"] for c in reviewed.get("conflicts", [])}
    new = [c for c in conflicts if c["id"] not in known]
    by = defaultdict(lambda: [0, 0])
    for r in results:
        if r["status"] != "not_checkable":
            by[r["check"]][r["status"] == "fail"] += 1
    for r in results:
        if r["status"] == "not_checkable":
            by[r["check"] + " (not checkable)"][0] += 1
    for c, (p, fl) in sorted(by.items()):
        print(f"{c:28} {p:6} pass {fl:5} fail")
    print(f"{len(conflicts)} conflicts, {len(new)} not yet in config/conflicts.yaml")
    return 1 if new else 0


# Stations whose generation and capacity make up MEW's and CSB's national totals.
# The RO units and boilers are consumers, not generators.
PLANTS_IN_TOTAL = {"shuwaikh", "shuaiba-north", "shuaiba-south", "doha-east", "doha-west", "zour-south",
                   "zour-north", "sabiya", "shagaya"}
