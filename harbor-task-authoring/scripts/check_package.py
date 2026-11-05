#!/usr/bin/env python3
"""Evalplat Harbor 题包本地预检（只用标准库，Python 3.11+）。

用法：python3 check_package.py <题包目录> [<题包目录> ...]

只做本地能查的：目录结构、脚本格式、编码、task.toml 字段、items.json 合计、答案是否泄漏进作答环境、包大小。
不替代 `evalplat check`（服务端解析）和真实回测。退出码：有错误 1，否则 0。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$")
JUDGE_MODELS = {"gemini-3.5-flash", "gemini-3.8-flash", "gpt-6.1-sol"}  # 平台代码默认允许列表，生产以实际配置为准
SKIP = {".git", "__pycache__", ".venv", "node_modules", ".DS_Store"}
MB = 1024 * 1024


class Report:
    def __init__(self, root: Path):
        self.root, self.errors, self.warns = root, [], []

    def err(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warns.append(msg)


def files_under(p: Path):
    for f in sorted(p.rglob("*")):
        if f.is_file() and not any(part in SKIP for part in f.relative_to(p).parts):
            yield f


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_script(r: Report, p: Path):
    if not p.exists():
        return
    raw = p.read_bytes()
    rel = p.relative_to(r.root)
    if not raw.startswith(b"#!"):
        r.err(f"{rel}：第一行缺 shebang（如 #!/bin/bash）")
    if b"\r\n" in raw:
        r.err(f"{rel}：CRLF 换行，会破坏 shebang；改成 LF")
    if raw.startswith(b"\xef\xbb\xbf"):
        r.err(f"{rel}：带 UTF-8 BOM，shebang 失效")


def check_text(r: Report, p: Path):
    try:
        p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        r.err(f"{p.relative_to(r.root)}：不是 UTF-8 编码")


def check_toml(r: Report) -> dict:
    p = r.root / "task.toml"
    if not p.exists():
        r.err("缺少 task.toml")
        return {}
    try:
        cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        r.err(f"task.toml 解析失败：{e}")
        return {}
    task = cfg.get("task", {})
    name = task.get("name", "")
    if not NAME_RE.match(name):
        r.err(f"[task] name={name!r} 不合法：要 org/name，字母数字和 ._-，字母或数字开头")
    arts = cfg.get("artifacts") or []
    if not arts:
        r.err("没有顶层 artifacts：独立判分容器拿不到作答文件（一般写 artifacts = [\"/app/output\"]）")
    for a in arts:
        src = a if isinstance(a, str) else (a or {}).get("source", "")
        if ".." in str(src):
            r.err(f"artifacts 路径不能含 ..：{src}")
    meta = cfg.get("metadata", {})
    if "execution" in meta:
        r.err("[metadata] execution 会被平台拒收")
    jm = meta.get("judge_model")
    if jm and jm not in JUDGE_MODELS:
        r.warn(f"judge_model={jm!r} 不在代码默认允许列表 {sorted(JUDGE_MODELS)} 中，确认生产已放行")
    sub = meta.get("subcategory")
    if sub and ("/" in sub or len(sub) > 100):
        r.err("[metadata] subcategory 不能含 / 且不超过 100 字")
    ver = cfg.get("verifier", {})
    if ver.get("environment_mode") != "separate":
        r.warn("[verifier] 没有显式写 environment_mode = \"separate\"（交付标准 S7 需要）")
    vt = float(ver.get("timeout_sec", 600))
    budget = (ver.get("env") or {}).get("GRADE_JUDGE_BUDGET")
    if budget and float(budget) >= vt:
        r.err(f"GRADE_JUDGE_BUDGET={budget} 不小于 verifier.timeout_sec={vt}，判分会被平台先杀掉")
    if jm and vt < 900:
        r.warn(f"模型判分题 verifier.timeout_sec={vt} 偏短")
    agent = cfg.get("agent", {})
    at = float(agent.get("timeout_sec", 36 * 3600))
    if at > 24 * 3600:
        r.warn(f"agent.timeout_sec={at} 超过 24 小时，云沙箱单次跑不完")
    env = cfg.get("environment", {})
    if env.get("os", "linux") != "linux":
        r.err("environment.os 只能是 linux")
    for k in ("tpu", "gpu_types"):
        if k in env:
            r.err(f"environment.{k} 会被平台拒收")
    if int(env.get("gpus", 0) or 0) > 0:
        r.err("平台不支持 GPU")
    for k, v in (env.get("env") or {}).items():
        if "${" in str(v):
            r.err(f"environment.env.{k} 不能写 ${{VAR}}")
    nm = env.get("network_mode", "public")
    if nm not in ("public", "no-network", "allowlist"):
        r.err(f"network_mode={nm!r} 只能是 public / no-network / allowlist")
    cpus = float(env.get("cpus", 1))
    mem_gb = float(env.get("memory_mb", 2048)) / 1024
    if cpus > 4 or mem_gb > 16:
        r.warn(f"资源 {cpus:g}c{mem_gb:g}g 超过云沙箱生产模板（最大 4c16g）")
    elif not (1 <= mem_gb / max(cpus, 1) <= 4):
        r.warn(f"云沙箱要求内存/CPU 比在 1~4 之间，当前 {mem_gb / max(cpus, 1):.2f}")
    if float(env.get("storage_mb", 10240)) > 15360:
        r.warn("storage_mb 超过 15360：云沙箱整盘 15G 且含镜像，平台不校验这个字段")
    if not (r.root / "environment" / "Dockerfile").exists() and not env.get("docker_image"):
        r.err("缺少 environment/Dockerfile（或 [environment] docker_image）")
    return cfg


def check_items(r: Report, cfg: dict):
    rub = r.root / "tests" / "rubric"
    ip = rub / "items.json"
    if not ip.exists():
        if cfg.get("metadata", {}).get("judge_model"):
            r.warn("声明了 judge_model，但没有 tests/rubric/items.json（如果不用模板判分程序可忽略）")
        return
    try:
        d = json.loads(ip.read_text(encoding="utf-8"))
    except Exception as e:
        r.err(f"items.json 解析失败：{e}")
        return
    if not (rub / "rubric.md").exists():
        r.err("tests/rubric/ 缺 rubric.md（专家细则原文）")
    if not (rub / "instruction.md").exists():
        r.err("tests/rubric/ 缺 instruction.md（题面副本，判分容器里读不到 /app 下的题面）")
    else:
        top = r.root / "instruction.md"
        if top.exists() and top.read_text(encoding="utf-8").strip() != (rub / "instruction.md").read_text(encoding="utf-8").strip():
            r.warn("tests/rubric/instruction.md 与顶层 instruction.md 不一致")
    groups = d.get("groups") or {}
    items = d.get("items") or []
    ids = [it.get("id") for it in items]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        r.err(f"items.json 评分项 ID 重复：{sorted(dup)}")
    for it in items:
        if it.get("group") not in groups:
            r.err(f"评分项 {it.get('id')} 的 group={it.get('group')!r} 不在 groups 里")
        for need in it.get("requires", []):
            if need not in ids:
                r.err(f"评分项 {it.get('id')} 的前提 {need} 不存在")
    total = sum(float(it.get("max", 0)) * float(groups.get(it.get("group"), {}).get("scale", 1.0)) for it in items)
    full = float(d.get("full", 100))
    has_extra = (rub / "extra.py").exists()
    if abs(total - full) > 0.01:
        if has_extra:
            r.warn(f"items 分值合计 {total:.4f} ≠ full {full}：差额应由 extra.py 的确定性评分项补齐，请核对")
        else:
            r.err(f"items 分值合计（含组折算）{total:.4f} ≠ full {full}")
    # batch 可以是 ID 列表，也可以是 {"ids": [...], ...}（新版判分程序）
    batched = [i for b in d.get("batches", []) for i in (b.get("ids", []) if isinstance(b, dict) else b)]
    det = not has_extra
    for i in ids:
        if i not in batched and det:
            r.err(f"评分项 {i} 不在任何 batch 里（又没有 extra.py 做确定性评分）")
    for i in batched:
        if i not in ids:
            r.err(f"batches 里的 {i} 不在 items 中")
    gt = d.get("gold_target")
    if gt and not (rub / "reference" / gt.get("file", "")).exists():
        r.err(f"gold_target 指向的 reference/{gt.get('file')} 不存在")
    ref = rub / "reference"
    if not ref.exists() or not any(ref.iterdir()):
        r.warn("tests/rubric/reference/ 为空：判分模型没有 Gold/评卷参考")


def check_leak(r: Report):
    env = r.root / "environment"
    if not env.exists():
        return
    env_hash = {}
    for f in files_under(env):
        if f.stat().st_size <= 200 * MB:
            env_hash.setdefault(sha256(f), f)
    secret_dirs = [r.root / "solution", r.root / "tests" / "rubric" / "reference"]
    for d in secret_dirs:
        if not d.exists():
            continue
        for f in files_under(d):
            if f.suffix in (".sh", ".py") or f.stat().st_size == 0 or f.stat().st_size > 200 * MB:
                continue
            h = sha256(f)
            if h in env_hash:
                r.err(f"答案泄漏：{f.relative_to(r.root)} 与作答环境里的 {env_hash[h].relative_to(r.root)} 内容相同")
    for f in files_under(env):
        low = f.name.lower()
        if any(k in low for k in ("rubric", "gold", "评分细则", "标准答案", "参考解")):
            r.warn(f"作答环境里有疑似答案文件：{f.relative_to(r.root)}（Agent 能看到）")


def check_instruction(r: Report):
    p = r.root / "instruction.md"
    if not p.exists():
        r.err("缺少 instruction.md")
        return
    t = p.read_text(encoding="utf-8", errors="replace")
    if "/tests" in t or "/solution" in t:
        r.err("instruction.md 里出现 /tests 或 /solution（Agent 看不到这些目录，也不该知道）")
    if "/app/output" not in t:
        r.warn("instruction.md 没写交付位置 /app/output/")
    for m in re.finditer(r"`(input/[^`]+)`", t):
        rel = m.group(1).rstrip("/")
        if not (r.root / "environment" / "input_files" / rel).exists():
            r.warn(f"题面引用的 {rel} 在 environment/input_files/ 下没找到（如果 Dockerfile 另有拷贝方式可忽略）")


def check_size(r: Report):
    total, data, count = 0, 0, 0
    for f in files_under(r.root):
        s = f.stat().st_size
        count += 1
        total += s
        if f.is_relative_to(r.root / "environment"):
            data += s
    if count > 20000:
        r.err(f"文件数 {count} 超过 20000")
    if total - data > 512 * MB:
        r.err(f"environment/ 以外 {(total - data) / MB:.0f}MB，超过 512MB")
    if total > 512 * MB:
        r.warn(f"整包 {total / MB:.0f}MB 超过 512MB：evalplat try 试跑会被拒，回测副本可删掉判分不读的大材料")
    return total


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bad = 0
    for a in argv:
        r = Report(Path(a).resolve())
        if not r.root.is_dir():
            print(f"✗ {a}：不是目录")
            bad = 1
            continue
        cfg = check_toml(r)
        check_instruction(r)
        if not (r.root / "tests" / "test.sh").exists():
            r.err("缺少 tests/test.sh")
        if not (r.root / "solution" / "solve.sh").exists():
            r.warn("没有 solution/solve.sh：跳过验收，交付标准 S4 缺参考解基线")
        for s in ("tests/test.sh", "solution/solve.sh"):
            check_script(r, r.root / s)
        for f in files_under(r.root):
            if f.suffix in (".md", ".toml", ".json", ".sh", ".py", ".csv") and f.stat().st_size < 50 * MB:
                check_text(r, f)
        check_items(r, cfg)
        check_leak(r)
        size = check_size(r)
        print(f"\n== {r.root.name}（{size / MB:.1f}MB）")
        for e in r.errors:
            print(f"  ✗ {e}")
        for w in r.warns:
            print(f"  ! {w}")
        if not r.errors and not r.warns:
            print("  ✓ 全部通过")
        elif not r.errors:
            print("  ✓ 无错误（有提醒，逐条确认）")
        bad |= bool(r.errors)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
