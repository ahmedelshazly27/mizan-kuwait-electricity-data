"""UNdata Energy Statistics rows (secondary source) as observations.

Consumption rows become `consumption` by sector; the supply-side rows keep a
UN-specific variable name (un_*) so they are never mistaken for MEW's own series,
whose definitions differ. They are used only for cross-checks."""

import json
from pathlib import Path

import yaml

from ..normalize import parse_printed
from ..records import Obs

SUPPLY = {
    "Electricity - Gross production": "un_gross_production",
    "Electricity - net production": "un_net_production",
    "Electricity - Own use by electricity, heat and CHP plants": "un_own_use_power_plants",
    "Electricity - Losses": "un_losses",
    "Electricity - imports": "un_imports",
    "Electricity - exports": "un_exports",
    "Electricity - Final energy consumption": "un_final_consumption",
    "Electricity - Energy industries own use": "un_energy_industries_own_use",
    "Electricity - Own use by oil refineries": "un_own_use_refineries",
    "Electricity - Own use by oil and gas extraction": "un_own_use_oil_gas",
}


def extract(path: Path, source_id: str, registry: Path) -> list[Obs]:
    data = json.loads(path.read_text())
    sectors = {s["un"]: s["id"] for s in yaml.safe_load((registry / "sectors.yaml").read_text())["sectors"]}
    notes = dict(n.split(" - ", 1) for n in [data["footnotes"]] if " - " in n)
    out = []
    for country, transaction, year, unit, qty, foot in data["rows"]:
        if transaction in sectors:
            variable, level, sector = "consumption", "sector", sectors[transaction]
        elif transaction in SUPPLY:
            variable, level, sector = SUPPLY[transaction], "national", None
        else:
            raise ValueError(f"UNdata transaction not mapped: {transaction}")
        value, status = parse_printed(qty)
        out.append(Obs(source_id, "EDATA", variable, level, f"{year}-01-01", f"{year}-12-31", "annual",
                       None if value is None else str(value), qty, status, unit, transaction, "Quantity",
                       "html_table", sector_id=sector,
                       footnote_printed=f"{foot} - {notes[foot]}" if foot in notes else (foot or None)))
    return out
