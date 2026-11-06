#!/bin/bash
# 参考解：把专家 Gold 原件原样拷到 /app/output/（不重存、不改动），再核对 SHA-256。
set -euo pipefail
mkdir -p /app/output
cp "/solution/golden_output/核查结论.md" /app/output/
echo "f63e588b663465736d81a2e26ca65040da945bddd4d2d3ac04237b9457cd04c9  /app/output/核查结论.md" | sha256sum -c -
