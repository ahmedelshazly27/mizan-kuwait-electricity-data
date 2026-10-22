"""MEW Statistical Year Book – Water: gross and net production of distilled water by
station and month (MIG, million imperial gallons).

Columns come from the edition config (`distilled_monthly.columns`, in printed order,
checked against the page image): each station or RO unit has a gross and a net
column, then the total. Each month's stations must sum to the printed total, and the
printed grand-total row must equal the sum of the months (both within rounding).
Thermal distillation (MSF; MED at Az-Zour North) and reverse osmosis are told apart
by the plant id (the *-ro plants)."""

import re
from pathlib import Path

from ..records import Obs
from .mew_text import page_text

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
NUM = r"-?\d+(?:\.\d+)?"


def extract(pdf: Path, cfg: dict) -> list[Obs]:
    c = cfg.get("distilled_monthly")
    if not c:
        return []
    cols = c["columns"]
    n = 2 * len(cols) + 2
    rows, grand = {}, None
    for line in page_text(pdf, c["page"]).splitlines():
        s = re.sub(r"[^\x00-\x7f]", " ", line).strip()
        vals = re.findall(rf"(?<![\w.]){NUM}(?![\w.])", s)
        head = s.split()[0] if s else ""
        if head in MONTHS and len(vals) == n:
            rows[MONTHS.index(head) + 1] = vals
        elif s.startswith("G.Total") and "MIG" in s and len(vals) == n:
            grand = vals
    if sorted(rows) != list(range(1, 13)) or grand is None:
        raise ValueError(f"{cfg['source_id']} p{c['page']}: months {sorted(rows)}, grand total {'found' if grand else 'missing'}")
    tol = 0.0015 * len(cols)              # values printed to 3 decimals (a few to 4)
    for m, v in rows.items():
        for k in (0, 1):
            parts = sum(float(v[2 * i + k]) for i in range(len(cols)))
            if abs(parts - float(v[-2 + k])) > tol:
                raise ValueError(f"{cfg['source_id']} month {m}: stations sum to {parts:.3f}, printed total {v[-2 + k]}")
    for j in range(n):
        tot = sum(float(rows[m][j]) for m in rows)
        if abs(tot - float(grand[j])) > 0.0015 * 12 + 0.002:
            raise ValueError(f"{cfg['source_id']}: column {j} months sum to {tot:.3f}, printed grand total {grand[j]}")
    y = cfg["data_year"]
    out = []
    for m, v in sorted(rows.items()):
        start, end = f"{y}-{m:02d}-01", f"{y}-{m:02d}-{[31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]:02d}"
        for i, col in enumerate(cols + [{"plant_id": None, "label": "Total"}]):
            for k, (var, lab) in enumerate((("water_production_gross", "Gross Prod."), ("water_production_net", "Net Prod."))):
                x = v[2 * i + k]
                out.append(Obs(cfg["source_id"], "distilled-monthly", var, "plant" if col["plant_id"] else "national",
                               start, end, "monthly", x, x, "number", "MIG", MONTHS[m - 1], f"{col['label']} / {lab}",
                               "pdf_text", plant_id=col["plant_id"], technology=col.get("technology"), page_pdf=c["page"]))
    return out
