"""Values read off the source pages by hand. Needs the source files (`kwelec fetch`);
skipped without them."""

import csv
from pathlib import Path

import pytest

OBS = Path(__file__).resolve().parents[1] / "data" / "interim" / "observations.csv"
pytestmark = pytest.mark.skipif(not OBS.exists(), reason="run `kwelec fetch && kwelec extract` first")

GOLDEN = [
    # source, table, variable, plant (None = national), period start, printed value
    ("mew-yb-2023", "generation-history", "generation_gross", None, "2023-01-01", "88017"),
    ("mew-yb-2023", "generation-history", "generation_gross", "zour-north", "2019-01-01", "13802.56"),
    ("mew-yb-2020", "generation-history", "generation_gross", "zour-north", "2019-01-01", "13803"),
    ("mew-yb-2023", "capacity-history", "installed_capacity", "shuaiba-south", "1994-01-01", "804+25"),
    ("mew-yb-2021", "capacity-history", "installed_capacity", None, "2019-01-01", "18793"),   # printed as is (shifted)
    ("mew-yb-2023", "peak-history", "peak_load_date", None, "2023-01-01", "08/02/2023"),
    ("mew-yb-2023", "net-export-monthly", "sent_out_net_total", None, "2023-01-01", "4167053"),
    ("csb-env-2024", "110", "generation_gross", None, "2024-01-01", "89,499,606"),
    ("csb-env-2024", "108", "installed_capacity", "sabiya", "2024-01-01", "6885.0"),
    ("mew-yb-2023", "station-units", "unit_capacity", "zour-south", "2023-01-01", "280 MW"),
    ("mew-yb-2023", "station-units", "unit_commissioning_year", "shuaiba-south", "2023-01-01", "07/ 06/ 1970"),
    ("mew-yb-2020", "station-units", "unit_commissioning_year", "zour-north", "2020-01-01", "26 / 11/ 2016**"),
    ("mew-yb-2023", "peak-day-load", "system_load", None, "2023-08-02T13:30:00+03:00", "16940"),
    ("mew-yb-2022", "peak-day-load", "system_load", None, "2022-08-10T00:00:00+03:00", "13740"),   # the closing 0:00 row
    ("mew-mb-2025-07", "daily-load", "peak_load_time", None, "2025-07-14", "13:30"),
    ("mew-mb-2025-07", "daily-load", "humidity_at_peak", None, "2025-07-01", "11%"),
    ("mew-mb-2025-05", "daily-load-compare", "max_load", None, "2024-05-01", "10260"),
    ("mew-yb-2023", "station-fuel-history", "fuel_energy", "doha-west", "2023-01-01", "115,140"),
    ("mew-yb-2023", "station-fuel-history", "fuel_cost", "zour-north", "2022-01-01", "372,525,921"),
]


def test_golden_values():
    rows = list(csv.DictReader(OBS.open()))
    for sid, tno, var, plant, p0, printed in GOLDEN:
        hits = [r for r in rows if r["source_id"] == sid and r["table_no"] == tno and r["variable"] == var
                and (r["plant_id"] or None) == plant and p0 in (r["period_start"], r["observed_at"])
                and r["frequency"] in ("annual", "monthly", "daily", "instant") and r["row_label"] not in ("Sub Total", "SubTotal")]
        assert printed in [r["value_printed"] for r in hits], (sid, tno, var, plant, p0, [r["value_printed"] for r in hits])


def test_regional_peak_rows():
    rows = [r for r in csv.DictReader(OBS.open()) if r["table_no"] == "regional-peak" and r["period_start"] == "2023-08-02"]
    got = {r["row_label"]: r["value_printed"] for r in rows}
    assert len(got) == 37 and got["3"] == "609" and got["33"] == "1428" and got["35"] == "349"
