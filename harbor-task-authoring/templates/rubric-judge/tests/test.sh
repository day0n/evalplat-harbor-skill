#!/bin/bash
# 按专家评分细则原文由判分模型逐项打分；判分模型不可用时不写 reward（平台记判分出错，不记 0 分）。
set -uo pipefail
mkdir -p /logs/verifier
python3 /tests/grader/rubric_verify.py \
  --task /tests/rubric \
  --instruction /tests/rubric/instruction.md \
  --workspace /app/output \
  --logs /logs/verifier
