"""The reviewed configs and the registries must agree with each other."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REG = {n: yaml.safe_load((ROOT / "registry" / f"{n}.yaml").read_text()) for n in ("plants", "variables", "units", "sectors")}
PLANTS = {p["id"] for p in REG["plants"]["plants"]}
VARIABLES = set(REG["variables"]["variables"])
UNITS = set(REG["units"]["units"])
SOURCES = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())["sources"]


def _columns(cfg):
    for t in cfg["tables"]:
        cols = t["columns"].values() if isinstance(t["columns"], dict) else t["columns"]
        for c in cols:
            yield t, c


def test_every_source_has_an_edition_config():
    for s in SOURCES:
        if s["tier"] == "primary":
            assert (ROOT / "config" / "editions" / f"{s['id']}.yaml").exists(), s["id"]


def test_config_references_exist():
    for f in (ROOT / "config" / "editions").glob("*.yaml"):
        cfg = yaml.safe_load(f.read_text())
        for t, c in _columns(cfg):
            if c.get("role") in ("period", "skip") or c.get("variable") == "notes":
                continue
            assert c.get("level") != "UNMAPPED", (f.name, c)
            assert c.get("variable", t.get("variable")) in VARIABLES, (f.name, c)
            if c.get("plant_id"):
                assert c["plant_id"] in PLANTS, (f.name, c)
            unit = c.get("unit_printed", t.get("unit_printed"))
            assert unit in UNITS, (f.name, unit)


def test_hashes_are_recorded():
    for s in SOURCES:
        assert len(s["sha256"]) == 64 and s["licence_note"], s["id"]
