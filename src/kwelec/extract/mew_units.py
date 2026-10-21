"""MEW yearbook station pages: one table per station listing every unit with its
date of commissioning and installed capacity, grouped under block headings
("Steam Turbines", "Combined Cycle Gas Turbines ZSCC (1)", ...).

Which pages belong to which station comes from the edition config (`station_pages`),
checked against the station total printed on the first page. For each unit two
observations are written:
  unit_capacity           MW, as printed
  unit_commissioning_year the year of the printed date; value_printed keeps the full
                          date exactly as printed (day and month are never parsed)
Technology is read from the block: a block with both gas and steam units is a
combined-cycle block; a block of steam units only is a steam plant; gas units only
are open-cycle gas turbines; Wind, CSP and PV rows are their own technology."""

import re
from pathlib import Path

from ..records import Obs
from .mew_text import page_text

STATION_TOTAL = re.compile(r"Installed Capacity\s+([\d.]+)\s*MW")
DATE = r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}"
UNIT = re.compile(rf"^\s*(No\s*\.?\s*\d+|GTG?\s*\d+|STG?\s*\d+|Wind|CSP|PV)\s+(\*{{0,2}})({DATE})(\*{{0,2}})\s+(?:MW\s+)?([\d.]+)\s*(?:MW)?\s*(\d)?\s*$")
HEADING = re.compile(r"(Turbines?|Combined Cycle)\b.*", re.I)


def _clean_heading(line: str) -> str:
    s = re.sub(r"[^\x00-\x7f]+", " ", line)          # drop the Arabic half of the bilingual heading
    s = re.sub(r"\((\w+)\(", r"(\1)", s)              # "ZSCC (1(" -> "ZSCC (1)" (RTL bracket in the text layer)
    return re.sub(r"\s+", " ", s).strip(" -·")


def _kind(label: str) -> str:
    if label.startswith(("No", "ST")):
        return "steam"
    if label.startswith("GT"):
        return "gas"
    return {"Wind": "wind", "CSP": "csp", "PV": "pv"}[label]


def extract(pdf: Path, cfg: dict) -> list[Obs]:
    out: list[Obs] = []
    year = cfg["data_year"]
    for station in cfg.get("station_pages", []):
        pages = station["pages"]
        first = page_text(pdf, pages[0])
        m = STATION_TOTAL.search(first)
        if not m or m.group(1) != station["total_printed"]:
            raise ValueError(f"{cfg['source_id']} {station['plant_id']}: station total on p{pages[0]} is "
                             f"{m.group(1) if m else None}, config says {station['total_printed']}")
        rows, block = [], None
        for p in pages:
            for line in page_text(pdf, p).splitlines():
                u = UNIT.match(line)
                if u:
                    rows.append((p, block or "(no heading)", re.sub(r"\s+", " ", u.group(1)).replace("No .", "No."),
                                 re.sub(r"\s+", " ", u.group(3)).strip(), u.group(2) or u.group(4), u.group(5)))
                elif HEADING.search(line) and "consists" not in line and "Date of Commissioning" not in line and len(line.strip()) < 120:
                    block = _clean_heading(line)
        for h in station.get("hidden_rows", []):   # reviewed: in the text layer, not visible on the page
            hit = [r for r in rows if r[0] == h["page"] and r[1] == h["block"]]
            if len(hit) != h["count"]:
                raise ValueError(f"{cfg['source_id']} {station['plant_id']}: expected {h['count']} hidden rows "
                                 f"in '{h['block']}' on p{h['page']}, found {len(hit)}")
            rows = [r for r in rows if r not in hit]
        if not rows:
            raise ValueError(f"{cfg['source_id']} {station['plant_id']}: no unit rows on pages {pages}")
        kinds: dict[str, set] = {}
        for _, b, label, *_ in rows:
            kinds.setdefault(b, set()).add(_kind(label))
        total = 0.0
        for p, b, label, date, marker, cap in rows:
            k, ks = _kind(label), kinds[b]
            tech = (k if k in ("wind", "csp", "pv") else
                    f"{k}_cc" if {"gas", "steam"} <= ks else
                    "steam" if k == "steam" else "ocgt")
            total += float(cap)
            common = dict(plant_id=station["plant_id"], unit_group=b, technology=tech, page_pdf=p,
                          footnote_printed=station.get("footnotes", {}).get(marker) if marker else None)
            lab = f"{b} / {label}"
            out.append(Obs(cfg["source_id"], "station-units", "unit_capacity", "unit", f"{year}-01-01", f"{year}-12-31",
                           "annual", cap, f"{cap} MW", "number", "MW", lab, "Installed Capacity", "pdf_text", **common))
            out.append(Obs(cfg["source_id"], "station-units", "unit_commissioning_year", "unit", f"{year}-01-01",
                           f"{year}-12-31", "annual", date[-4:], date + marker, "number", "year", lab,
                           "Date of Commissioning", "pdf_text", **common))
        if abs(total - float(station["total_printed"])) > 0.05:
            raise ValueError(f"{cfg['source_id']} {station['plant_id']}: units sum to {total:g} MW, "
                             f"the station page prints {station['total_printed']}")
    return out
