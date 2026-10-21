"""kwelec: rebuild the Kuwait Electricity Open Dataset from its sources.

    kwelec fetch       download every source in config/sources.yaml into data/raw/
    kwelec extract     every printed cell -> data/interim/observations.csv
    kwelec validate    checks -> data/out/validation.csv, data/out/conflicts.csv
    kwelec build       downloads (data/out/) and page data (data/web/)
    kwelec load        load data/out/ into the database (needs SUPABASE_PROJECT_REF)
    kwelec all         fetch, extract, validate, build
"""

import argparse
import csv
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM, OUT, WEB = (ROOT / "data" / d for d in ("raw", "interim", "out", "web"))
CONFIG, REGISTRY = ROOT / "config", ROOT / "registry"


def sources() -> list[dict]:
    return yaml.safe_load((CONFIG / "sources.yaml").read_text())["sources"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_fetch(args) -> int:
    import requests

    from .fetch import csb, undata

    RAW.mkdir(parents=True, exist_ok=True)
    session, changed = requests.Session(), []
    for s in sources():
        dest = RAW / s["file"]
        if dest.exists() and not args.force:
            print(f"have  {s['id']}")
        else:
            f = s["fetch"]
            if f["method"] == "http":
                # mew.gov.kw needs legacy TLS renegotiation; certificate checks stay on.
                env = dict(os.environ, OPENSSL_CONF=str(CONFIG / "openssl-mew.cnf")) if f.get("legacy_tls") else None
                subprocess.run(["curl", "-sSf", "--retry", "3", "--max-time", "900", "-o", str(dest), f["url"]],
                               check=True, env=env)
            elif f["method"] == "csb_postback":
                content, _, _ = csb.download(session, f["page_id"], f["parent"], f["year"], f["chapter"])
                dest.write_bytes(content)
            elif f["method"] == "undata":
                import json
                _, rows, notes = undata.fetch(session)
                dest.write_text(json.dumps({"rows": rows, "footnotes": notes}, ensure_ascii=False))
            print(f"got   {s['id']}")
        if sha256(dest) != s["sha256"]:
            changed.append(s["id"])
    if changed:
        print("\nThese files differ from the hash in config/sources.yaml (a new version, or a changed page):")
        print("  " + "\n  ".join(changed))
        print("They are not used until the owner reviews them and the hash is updated.")
        return 1
    return 0


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


def cmd_extract(args) -> int:
    from .extract import csb_env, mew_text, mew_units, undata
    from .records import FIELDS

    obs = []
    for s in sources():
        path = RAW / s["file"]
        if sha256(path) != s["sha256"]:
            sys.exit(f"{s['id']}: file does not match its recorded sha256; run `kwelec fetch` and review")
        if s["id"].startswith("csb-env-"):
            obs += csb_env.extract(path, yaml.safe_load((CONFIG / "editions" / f"{s['id']}.yaml").read_text()))
        elif s["id"].startswith("mew-"):
            cfg = yaml.safe_load((CONFIG / "editions" / f"{s['id']}.yaml").read_text())
            obs += mew_text.extract(path, cfg)
            obs += mew_units.extract(path, cfg)
        elif s["id"].startswith("undata-"):
            obs += undata.extract(path, s["id"], REGISTRY)
        print(f"{s['id']:22} {sum(o.source_id == s['id'] for o in obs):6} cells")
    # ids follow config/sources.yaml order and each source's table and cell order, so a rebuild
    # from the same files gives the same ids.
    _write(INTERIM / "observations.csv", [{"id": i, **o.row()} for i, o in enumerate(obs, 1)], ["id"] + FIELDS)
    print(f"{len(obs)} observations -> {INTERIM / 'observations.csv'}")
    return 0


def cmd_validate(args) -> int:
    from .validate import run

    return run(INTERIM / "observations.csv", OUT, REGISTRY, CONFIG)


def cmd_build(args) -> int:
    from .build import outputs

    return outputs.build(INTERIM / "observations.csv", OUT, WEB, CONFIG, REGISTRY)


def cmd_load(args) -> int:
    from .load import supabase

    return supabase.load(OUT, ROOT / "migrations", apply_migrations=args.migrate)


def main() -> None:
    p = argparse.ArgumentParser(prog="kwelec", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--force", action="store_true", help="download again even if the file exists")
    sub.add_parser("extract")
    sub.add_parser("validate")
    sub.add_parser("build")
    lo = sub.add_parser("load")
    lo.add_argument("--migrate", action="store_true", help="apply migrations/*.sql not yet applied")
    a = sub.add_parser("all")
    a.set_defaults(force=False)
    args = p.parse_args()
    if args.cmd == "all":
        for c in (cmd_fetch, cmd_extract, cmd_validate, cmd_build):
            rc = c(args)
            if rc:
                sys.exit(rc)
        return
    sys.exit({"fetch": cmd_fetch, "extract": cmd_extract, "validate": cmd_validate, "build": cmd_build,
              "load": cmd_load}[args.cmd](args))


if __name__ == "__main__":
    main()
