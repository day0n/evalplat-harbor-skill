#!/bin/bash
# 确定性判分：逐家公司比对，容差 0.0001；每条路径都写 reward（0~1）。
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/reward.json
python3 - <<'PY'
import json
EXPECTED = {"A公司": 0.65, "B公司": 0.40}   # 标准答案只放在 tests/ 里，Agent 看不到
TOL = 1e-4
checks, got = [], {}
try:
    got = json.load(open("/app/output/answer.json", encoding="utf-8"))
except Exception as e:
    print(f"读不到 answer.json：{e}")
for k, v in EXPECTED.items():
    try:
        ok = abs(float(got.get(k)) - v) <= TOL
    except (TypeError, ValueError):
        ok = False
    checks.append({"id": k, "passed": ok, "weight": 1, "message": f"期望 {v}，实际 {got.get(k)}"})
reward = sum(c["passed"] for c in checks) / len(checks)
json.dump({"checks": checks}, open("/logs/verifier/checks.json", "w"), ensure_ascii=False)
json.dump({"reward": reward}, open("/logs/verifier/reward.json", "w"))
print(f"reward = {reward}")
PY
