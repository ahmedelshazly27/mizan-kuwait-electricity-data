"""System load below annual resolution, from MEW's own tables.

Yearbooks (`peak_day_curve` in the edition config): the half-hourly system load on
the day of the yearly peak, printed beside the station table on that page. The
column runs 00.00, 0:30, ... 23:00 and ends with 0:00, the end of the day; there is
no 23:30 row. Each value is a load at an instant (frequency `instant`, the time in
`observed_at`, Kuwait local time, UTC+03:00 all year); the closing 0:00 is stamped
at 00:00 of the next day. The curve's maximum must equal the peak
printed in the config (checked against the page by hand).

Monthly books (`daily_load`): one row per day with available capacity, plant on
bars, spinning reserve, ISR, the peak load with its time, temperature and humidity,
and the minimum load with its time, temperature and humidity. The printed Max. and
Min. rows are not stored; they are used as checks. Books without that table print
a comparison instead (`daily_compare`): maximum load, minimum load and maximum
temperature for each day of the month in this year and the year before. Its
percentage-change columns are derived and serve only as checks."""

import re
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

from ..records import Obs
from .mew_text import page_text

CURVE = re.compile(r"^\s{0,16}(\d{1,2}[.:]\d{2})\s+(\d{4,5})\b")
N, T, P = r"(\d{1,5})", r"(\d{1,2}:\d{2})", r"(\d{1,3})%"
DAY = re.compile(rf"^\s*(\d{{1,2}})\s+{N}\s+{N}\s+{N}\s+{N}\s+{N}\s+{T}\s+{N}\s+{P}\s+{N}\s+{T}\s+{N}\s+{P}\s*$")
MAX = re.compile(rf"^\s*Max\.\s+{N}\s+{N}\s+{N}\s+{N}\s+{N}\s+{T}\s+{N}\s+{P}\s*$")
MIN = re.compile(rf"^\s*Min\.\s+{N}\s+{N}\s+{N}\s+{N}\s+{N}\s+{T}\s+{N}\s+{P}\s*$")

# Printed columns of the daily table, left to right after the date.
DAILY = [("available_capacity", "Available Capacity (MW)", "MW"), ("plant_on_bars", "Plant on Bars (MW)", "MW"),
         ("spinning_reserve", "Spinning Reserve (MW)", "MW"), ("isr", "ISR (MW)", "MW"),
         ("peak_load", "Peak Load (MW)", "MW"), ("peak_load_time", "Time", "time"),
         ("temperature_at_peak", "Max. Temp. Co", "Co"), ("humidity_at_peak", "Max.Rel.Humidity %", "%"),
         ("min_load", "Min. Load (MW)", "MW"), ("min_load_time", "Time", "time"),
         ("temperature_at_min", "Min. Temp. Co", "Co"), ("humidity_at_min", "Min.Rel. Humidity %", "%")]


def _curve(pdf: Path, cfg: dict) -> list[Obs]:
    c = cfg["peak_day_curve"]
    day = date.fromisoformat(str(c["date"]))
    text = page_text(pdf, c["page"])
    if c["title_printed"] not in text:
        raise ValueError(f"{cfg['source_id']} p{c['page']}: title '{c['title_printed']}' not found")
    rows = [CURVE.match(line).groups() for line in text.splitlines() if CURVE.match(line)]
    expect = ["00.00"] + [f"{h}:{m:02d}" for h in range(24) for m in (0, 30) if (h, m) not in ((0, 0), (23, 30))] + ["0:00"]
    if [t for t, _ in rows] != expect:
        raise ValueError(f"{cfg['source_id']} p{c['page']}: curve times are {[t for t, _ in rows]}, expected {expect}")
    if max(int(v) for _, v in rows) != int(c["peak_printed"]):
        raise ValueError(f"{cfg['source_id']} p{c['page']}: curve maximum is not the printed peak {c['peak_printed']}")
    out = []
    for i, (t, v) in enumerate(rows):
        d = day + timedelta(days=1) if i == len(rows) - 1 else day
        h, m = (int(x) for x in t.replace(".", ":").split(":"))
        out.append(Obs(cfg["source_id"], "peak-day-load", "system_load", "national", d.isoformat(), d.isoformat(),
                       "instant", v, v, "number", "MW", t, "Peak Load (MW)", "pdf_text", page_pdf=c["page"],
                       observed_at=f"{d.isoformat()}T{h:02d}:{m:02d}:00+03:00"))
    return out


def _daily(pdf: Path, cfg: dict) -> list[Obs]:
    c = cfg["daily_load"]
    y, mo = cfg["data_year"], cfg["data_month"]
    days, mx, mn = {}, None, None
    for p in c["pages"]:
        for line in page_text(pdf, p).splitlines():
            if m := DAY.match(line):
                days[int(m.group(1))] = (p, m.groups()[1:])
            elif m := MAX.match(line):
                mx = m.groups()
            elif m := MIN.match(line):
                mn = m.groups()
    n = monthrange(y, mo)[1]
    if sorted(days) != list(range(1, n + 1)):
        raise ValueError(f"{cfg['source_id']}: daily load rows for days {sorted(days)}, expected 1..{n}")
    cols = list(zip(*(v for _, v in days.values())))
    # Max. row: the maxima of the first eight columns; Min. row: the minima of the four
    # capacity columns, then of the minimum-load columns (times compared as printed).
    key = lambda s: tuple(int(x) for x in s.split(":")) if ":" in s else int(s)
    want_max = [max(col, key=key) for col in cols[:8]]
    want_min = [min(col, key=key) for col in cols[:4]] + [min(col, key=key) for col in cols[8:]]
    for label, printed, want in (("Max.", mx, want_max), ("Min.", mn, want_min)):
        if printed is None or [key(x) for x in printed] != [key(x) for x in want]:
            raise ValueError(f"{cfg['source_id']}: printed {label} row {printed} does not match the daily rows {want}")
    out = []
    for d, (p, vals) in sorted(days.items()):
        ds = date(y, mo, d).isoformat()
        for (var, col, unit), v in zip(DAILY, vals):
            num = None if unit == "time" else v
            printed = v + "%" if unit == "%" else v
            out.append(Obs(cfg["source_id"], "daily-load", var, "national", ds, ds, "daily", num, printed,
                           "text" if unit == "time" else "number", unit, str(d), col, "pdf_text", page_pdf=p))
    return out


F = r"(-?\d{1,3}\.\d)"
COMPARE = re.compile(rf"^\s*(\d{{1,2}})\s+{N}\s+{N}\s+{F}\s+{N}\s+{N}\s+{F}\s+{N}\s+{N}\s*$")


def _compare(pdf: Path, cfg: dict) -> list[Obs]:
    c = cfg["daily_compare"]
    y, mo = cfg["data_year"], cfg["data_month"]
    text = page_text(pdf, c["page"])
    if "Comparative maximum & minimum loads" not in text:
        raise ValueError(f"{cfg['source_id']} p{c['page']}: not the comparative load table")
    days = {int(m.group(1)): m.groups()[1:] for line in text.splitlines() if (m := COMPARE.match(line))}
    n = monthrange(y, mo)[1]
    if sorted(days) != list(range(1, n + 1)):
        raise ValueError(f"{cfg['source_id']}: comparative rows for days {sorted(days)}, expected 1..{n}")
    out = []
    for d, (mx, mx0, pmx, mn, mn0, pmn, t, t0) in sorted(days.items()):
        for new, old, pct in ((mx, mx0, pmx), (mn, mn0, pmn)):
            if abs((int(new) - int(old)) / int(old) * 100 - float(pct)) > 0.051:
                raise ValueError(f"{cfg['source_id']} day {d}: {new} vs {old} is not the printed change {pct}%")
        for yy, vals in ((y, (mx, mn, t)), (y - 1, (mx0, mn0, t0))):
            ds = date(yy, mo, d).isoformat()
            for var, col, unit, v in zip(("max_load", "min_load", "max_temperature"),
                                         ("Max. Load", "Min. Load", "Max.Temp. C"), ("MW", "MW", "ºC"), vals):
                out.append(Obs(cfg["source_id"], "daily-load-compare", var, "national", ds, ds, "daily", v, v,
                               "number", unit, str(d), f"{col} / {yy}", "pdf_text", page_pdf=c["page"]))
    return out


def extract(pdf: Path, cfg: dict) -> list[Obs]:
    return ((_curve(pdf, cfg) if "peak_day_curve" in cfg else []) + (_daily(pdf, cfg) if "daily_load" in cfg else [])
            + (_compare(pdf, cfg) if "daily_compare" in cfg else []))
