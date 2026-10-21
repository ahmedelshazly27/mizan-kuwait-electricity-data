"""MEW Statistical Year Book tables from the PDF text layer.

The text layer's column headers are unreliable (misaligned, sometimes mislabelled)
and empty cells are not printed at all, so column identity comes from
config/editions/mew-yb-<year>.yaml and from position: for each table, the PDF page,
a title that must appear on that page, the kind of rows, the columns left to right
as reviewed by hand, and an anchor row whose cells fill every column. Every other
row's cells are assigned to the nearest anchor column by horizontal position; a cell
that is not clearly under one column stops the run. A column with nothing printed
in a row becomes a blank observation."""

import calendar
import re
from pathlib import Path

import subprocess

from ..normalize import INVISIBLE, clean, parse_printed
from ..records import Obs

DATE = r"\d{1,2}(?:\s?&\s?\d{1,2})?/\d{1,2}/\d{4}"
COMPOSITE = r"\)?\d+(?:\.\d+)?\s?\+\s?\(?\d+\)?"
NUM = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
CELL = re.compile(rf"(\*{{1,3}})?\s?({DATE}|{COMPOSITE}|{NUM}|[-–_])\s?(\*{{1,3}})?")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
TOTALS = {"Sub Total": "half", "SubTotal": "half", "G. Total": "year", "Grand Total": "year", "Total": "year"}


def page_text(pdf: Path, page: int) -> str:
    """pdftotext -layout keeps rotated pages and column positions; the bidi control
    characters it adds around numbers are removed (they carry no content)."""
    out = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    return INVISIBLE.sub("", out)


TOKEN = re.compile(r"\S+")


def row_cells(line: str) -> tuple[str, list[dict]]:
    """(the line, its cells with printed text, marker and character-column centre).
    Cells are whitespace-separated, except that the pieces of a composite such as
    "720 +25" or ")720 +(25" and a separated footnote marker ("* 66356") are joined."""
    line = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", line)        # 'الكلى358065' -> 'الكلى 358065'
    toks = [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(line)]
    merged: list[list] = []
    for t, a, b in toks:
        prev = merged[-1] if merged else None
        if prev and (re.fullmatch(r"\+\(?\d+\)?", t) or re.fullmatch(r"\*{1,3}", prev[0])):
            prev[0], prev[2] = prev[0] + " " + t, b
        else:
            merged.append([t, a, b])
    cells = []
    for t, a, b in merged:
        m = CELL.fullmatch(t)
        if m:
            cells.append({"printed": m.group(2), "marker": m.group(1) or m.group(3), "x": (a + b) / 2})
    return line, cells


def _label(text: str) -> str | None:
    for m in MONTHS:
        if re.match(rf"{m}\b", text):
            return m
    for t in TOTALS:
        if text.startswith(t):
            return t
    return None


def _period(kind: str, label, year: int, half: int, month: int | None = None) -> tuple[str, str, str]:
    if kind == "days":
        if label == "Total":
            return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}", "monthly"
        return f"{year}-{month:02d}-{label:02d}", f"{year}-{month:02d}-{label:02d}", "daily"
    if kind == "years":
        return f"{label}-01-01", f"{label}-12-31", "annual"
    if label in MONTHS:
        m = MONTHS.index(label) + 1
        return f"{year}-{m:02d}-01", f"{year}-{m:02d}-{calendar.monthrange(year, m)[1]:02d}", "monthly"
    if TOTALS[label] == "half":
        return (f"{year}-01-01", f"{year}-06-30", "half_year") if half == 1 else (f"{year}-07-01", f"{year}-12-31", "half_year")
    return f"{year}-01-01", f"{year}-12-31", "annual"


def _norm_label(lab) -> object:
    return {"year": "Total", "half": "Sub Total"}.get(TOTALS.get(lab), lab) if isinstance(lab, str) else lab


def table_rows(texts: list[tuple[int, str]], t: dict) -> list[tuple[object, str, list[dict], int]]:
    rows = []
    expecting_total = False
    for page, line in ((p, line) for p, x in texts for line in x.splitlines()):
        text, cs = row_cells(line)
        if t["rows"] == "days" and text.strip() == "Total":   # the monthly books print the label on its own line
            expecting_total = True
            continue
        if not cs:
            continue
        if t["rows"] == "years":
            if re.search(r"During|خلال|خالل", text) or len(cs) < 3:
                continue
            ys = [c for c in cs if re.fullmatch(r"(19|20)\d\d", c["printed"])]
            if not ys:
                continue
            year_cell = ys[-1] if t.get("year_side", "right") == "right" else ys[0]
            y = int(year_cell["printed"])
            if t["years"][0] <= y <= t["years"][1]:
                rows.append((y, text, cs, page))
        elif t["rows"] == "days":
            first = text.split()[0] if text.split() else ""
            if re.fullmatch(r"\d{1,2}", first) and cs and cs[0]["printed"] == first and len(cs) > 3:
                rows.append((int(first), text, cs, page))
            elif (expecting_total or first == "Total") and len(cs) > 3:
                rows.append(("Total", text, cs, page))
                break
        else:
            lab = _label(text.strip())
            if lab:
                rows.append((lab, text, cs, page))
    return rows


def extract(pdf_path: Path, cfg: dict) -> list[Obs]:
    out: list[Obs] = []
    for t in cfg["tables"]:
        pages = t["page_pdf"] if isinstance(t["page_pdf"], list) else [t["page_pdf"]]
        texts = [(p, page_text(pdf_path, p)) for p in pages]
        if not all(re.sub(r"\s+", " ", t["title_en"]) in re.sub(r"\s+", " ", clean(x)) for _, x in texts):
            raise ValueError(f"{cfg['source_id']} {t['id']}: title not on page {t['page_pdf']}")
        out += _table(cfg, t, texts)
    return out


def _table(cfg: dict, t: dict, texts: list[tuple[int, str]]) -> list[Obs]:
    cols = t["columns"]
    rows = table_rows(texts, t)
    labels = [_norm_label(r[0]) for r in rows]
    if t["rows"] == "years":
        want = list(range(t["years"][0], t["years"][1] + 1))
    elif t["rows"] == "days":
        want = list(range(1, calendar.monthrange(cfg["data_year"], cfg["data_month"])[1] + 1)) + ["Total"]
    else:
        want = MONTHS[:6] + ["Sub Total"] + MONTHS[6:] + ["Sub Total", "Total"]
    if labels != want:
        raise ValueError(f"{cfg['source_id']} {t['id']}: rows {labels} != {want}")
    anchor = next(cs for lab, _, cs, _ in rows if _norm_label(lab) == t["anchor_row"])
    if len(anchor) != len(cols):
        raise ValueError(f"{cfg['source_id']} {t['id']}: anchor row has {len(anchor)} cells, config {len(cols)}")
    # Monthly tables have every cell filled, and pdftotext packs crowded lines, so their
    # cells are taken in order; year tables leave cells empty, so they go by position.
    align = t.get("align", "position" if t["rows"] == "years" else "order")
    xs = [c["x"] for c in anchor]
    tol = min(b - a for a, b in zip(xs, xs[1:])) * 0.45
    out = []
    half = 0
    for lab, text, cs, page in rows:
        if TOTALS.get(lab) == "half":
            half += 1
        placed: dict[int, dict] = {}
        for stray in t.get("strays", []):   # reviewed: text in the PDF that is not a table cell
            if str(stray["row"]) == str(lab):
                hit = [c for c in cs if c["printed"] == stray["printed"]]
                if len(hit) != 1:
                    raise ValueError(f"{cfg['source_id']} {t['id']} row {lab}: listed stray {stray['printed']} not found")
                cs = [c for c in cs if c is not hit[0]]
        if t["rows"] == "days" and lab == "Total":   # the total row has no date cell
            cs = [None] + cs
        if align == "order":
            if len(cs) != len(cols):
                raise ValueError(f"{cfg['source_id']} {t['id']} row {lab}: {len(cs)} cells, config {len(cols)}\n{text.strip()}")
            placed = {i: c for i, c in enumerate(cs) if c is not None}
        for c in (cs if align == "position" else []):
            i = min(range(len(xs)), key=lambda k: abs(xs[k] - c["x"]))
            if abs(xs[i] - c["x"]) > tol or i in placed:
                raise ValueError(f"{cfg['source_id']} {t['id']} row {lab}: cell {c['printed']!r} at x={c['x']:.0f} "
                                 f"does not sit under one column (anchors {[round(x) for x in xs]})\n{text.strip()}")
            placed[i] = c
        p0, p1, freq = _period(t["rows"], lab, cfg["data_year"], half, cfg.get("data_month"))
        for i, col in enumerate(cols):
            c = placed.get(i)
            if col.get("role") == "period":
                if (c is None) != (lab == "Total" and t["rows"] == "days") or (c and c["printed"] != str(lab)):
                    raise ValueError(f"{cfg['source_id']} {t['id']}: period cell for {lab} is {c}")
                continue
            if col.get("role") == "skip":
                continue
            printed = c["printed"] if c else ""
            marker = c["marker"] if c else None
            value, status = parse_printed(printed)
            if col.get("text") and status != "blank":   # dates: kept as printed, never parsed
                value, status = None, "text"
            out.append(Obs(cfg["source_id"], t["table_no"] or t["id"], col["variable"], col.get("level", "plant"),
                           p0, p1, freq, None if value is None else str(value),
                           (f"{marker} {printed}" if marker else printed), status,
                           col.get("unit_printed", t["unit_printed"]), str(lab), col["label"], "pdf_text",
                           plant_id=col.get("plant_id"), technology=col.get("technology"),
                           unit_group=col.get("unit_group"), page_pdf=page,
                           page_printed=t.get("page_printed"),
                           footnote_printed=t.get("footnotes", {}).get(marker) if marker else None))
    return out
