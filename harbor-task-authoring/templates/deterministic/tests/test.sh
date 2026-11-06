#!/bin/bash
# 按 tests/rubric/rubric.json 判分：本题全部评分项由程序比对（method=code），不调用判分模型。
set -uo pipefail
mkdir -p /logs/verifier
python3 /tests/grader/rubric_verify.py \
  --task /tests/rubric \
  --instruction /tests/rubric/instruction.md \
  --workspace /app/output \
  --logs /logs/verifier
