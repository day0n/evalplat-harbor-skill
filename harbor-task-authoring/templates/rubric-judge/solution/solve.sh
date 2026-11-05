#!/bin/bash
# 参考解：把专家 Gold 原件原样拷到 /app/output/（不重存、不改动），再核对 SHA-256。
set -euo pipefail
mkdir -p /app/output
cp "/solution/golden_output/核查结论.md" /app/output/
echo "4677e36001bfdde910fb97fb6bbd36d8c966a0dec7259f72f24451da9b4fc9f8  /app/output/核查结论.md" | sha256sum -c -
