#!/bin/bash
set -euo pipefail
mkdir -p /app/output
python3 - <<'PY'
import csv, json
rows = csv.DictReader(open("/app/input/balance.csv", encoding="utf-8"))
ans = {r["company"]: round(float(r["total_liabilities"]) / float(r["total_assets"]), 4) for r in rows}
json.dump(ans, open("/app/output/answer.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
