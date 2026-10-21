"""Load data/out/ into the Supabase project through the Management API.

Direct Postgres connections may be blocked where this runs, so SQL goes through
POST /v1/projects/{ref}/database/query. Migrations are the files in migrations/,
applied in name order and recorded in pipeline.migrations. Data is replaced in full
on every load. Credentials: SUPABASE_ACCESS_TOKEN if set (otherwise the request goes
out without one, for environments whose proxy adds it); the token is never printed."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

API = "https://api.supabase.com/v1/projects/{ref}/database/query"
BATCH = 1500

# Load order (parents first); deleted in reverse.
TABLES = [
    ("sources", "sources.csv"), ("source_tables", "source_tables.csv"), ("variables", "variables.csv"),
    ("units", "units.csv"), ("fuels", "fuels.csv"), ("plants", "plants.csv"), ("plant_aliases", "plant_aliases.csv"),
    ("sectors", "sectors.csv"), ("observations", "observations.csv"), ("conflicts", "conflicts.csv"),
    ("conflict_members", None), ("validation_results", "validation.csv"),
]
COLUMNS = {
    "observations": None,   # every column of the table, from the CSV header minus the canonical columns
    "conflicts": ["id", "grp", "kind", "key", "canonical_values", "unit", "spread", "status", "decision",
                  "decided_by", "decided_at", "group_note"],
}


class Client:
    def __init__(self, ref: str):
        self.url = API.format(ref=ref)
        self.s = requests.Session()
        token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def sql(self, query: str):
        r = self.s.post(self.url, json={"query": query}, timeout=300)
        if r.status_code >= 300:
            raise RuntimeError(f"database query failed ({r.status_code}): {r.text[:500]}")
        return r.json()


def _plants_first(rows: list[dict]) -> list[dict]:
    # plants.parent references plants: parents before children
    return sorted(rows, key=lambda r: bool(r.get("parent")))


def _rows(out: Path, table: str, file: str | None) -> list[dict]:
    if table == "conflict_members":
        return [{"conflict_id": c["id"], "observation_id": m}
                for c in csv.DictReader((out / "conflicts.csv").open()) for m in c["members"].split()]
    rows = list(csv.DictReader((out / file).open()))
    if table == "observations":
        for r in rows:
            r.pop("canonical_value"), r.pop("canonical_unit")
    if table == "conflicts":
        rows = [{"grp": r["group"], **{k: r[k] for k in COLUMNS["conflicts"] if k != "grp"}} for r in rows]
    if table == "validation_results":
        rows = [{"id": i, "check_name": r["check"], "scope": r["scope"], "status": r["status"], "detail": r["detail"]}
                for i, r in enumerate(rows, 1)]
    if table == "plants":
        rows = _plants_first(rows)
    for r in rows:
        for k, v in r.items():
            if v == "" and k != "value_printed":   # a blank printed cell keeps its empty printed string
                r[k] = None
            elif k in ("pages_pdf", "seen_in") and v:
                r[k] = json.loads(v)
    return rows


def _insert(db: Client, table: str, rows: list[dict]) -> None:
    for i in range(0, len(rows), BATCH):
        payload = json.dumps(rows[i:i + BATCH], ensure_ascii=False)
        if "$kwelec$" in payload:
            raise ValueError("payload contains the dollar-quote tag")
        db.sql(f"insert into public.{table} select * from jsonb_populate_recordset(null::public.{table}, $kwelec${payload}$kwelec$::jsonb)")


def load(out: Path, migrations: Path, apply_migrations: bool) -> int:
    ref = os.environ.get("SUPABASE_PROJECT_REF")
    if not ref:
        sys.exit("set SUPABASE_PROJECT_REF")
    db = Client(ref)
    if apply_migrations:
        db.sql("create schema if not exists pipeline; create table if not exists pipeline.migrations "
               "(name text primary key, applied_at timestamptz not null default now())")
        done = {r["name"] for r in db.sql("select name from pipeline.migrations")}
        for f in sorted(migrations.glob("*.sql")):
            if f.name in done:
                continue
            sql = f.read_text()
            db.sql(f"begin; {sql}\n; insert into pipeline.migrations (name) values ('{f.name}'); commit;")
            print(f"applied {f.name}")

    for table, _ in reversed(TABLES):
        db.sql(f"delete from public.{table}")
    db.sql("delete from public.builds")
    total = 0
    for table, file in TABLES:
        rows = _rows(out, table, file)
        _insert(db, table, rows)
        total += len(rows)
        print(f"loaded {table:20} {len(rows):6}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "uncommitted"
    n = db.sql("select count(*) as n from public.observations")[0]["n"]
    db.sql(f"insert into public.builds (id, built_at, observations) values ('{commit}', now(), {int(n)})")
    print(f"{total} rows; build {commit[:10]}")
    return 0
