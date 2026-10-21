#!/usr/bin/env bash
# Publish the source documents as the `sources-2026-10-21` release (run once, by the
# owner, from a checkout with data/raw/ fetched: `uv run kwelec fetch`).
# Verifies every file against config/sources.yaml before uploading.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=sources-2026-10-21
OUT=$(mktemp -d)
uv run python - "$OUT" <<'PY'
import hashlib, shutil, sys, yaml
out = sys.argv[1]
for s in yaml.safe_load(open("config/sources.yaml"))["sources"]:
    if s["tier"] != "primary":
        continue
    data = open(f"data/raw/{s['file']}", "rb").read()
    if hashlib.sha256(data).hexdigest() != s["sha256"]:
        sys.exit(f"{s['file']}: hash differs from config/sources.yaml")
    shutil.copy(f"data/raw/{s['file']}", out)
PY
(cd "$OUT" && sha256sum *.pdf *.xlsx > SHA256SUMS)
cp scripts/NOTICE-sources.txt "$OUT/NOTICE.txt"
gh release create "$TAG" --target main --title "Source documents, retrieved 2026-10-21" \
  --notes "Unmodified copies of the primary documents the dataset is built from, with SHA256SUMS. They belong to their publishers; see NOTICE.txt. This release holds sources only, not the dataset." \
  "$OUT"/NOTICE.txt "$OUT"/SHA256SUMS "$OUT"/*.pdf "$OUT"/*.xlsx
