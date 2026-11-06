"""method=code 的评分项：存在性、数值、单元格、JSON 值等确定性检查。

每个检查返回 (value, evidence, reason)：
- 正向项：value 为 0~1（binary 只有 0/1；python 检查可返回 gradient 档位）；
- 负向项：value 为命中次数（binary 未设 max_hits 时 0/1）。
数值检查必须绑定上下文（同一行里同时出现 context 各词，可再要求单位），不做“全文搜到数字就算对”。
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
from pathlib import Path

NUM_RE = re.compile(r"(?<![\d.])[-−+]?\d[\d,，]*(?:\.\d+)?")


def _nums(line: str, unit: str | None = None) -> list[float]:
    out = []
    for m in NUM_RE.finditer(line):
        if unit and not line[m.end():].lstrip().startswith(unit):
            continue
        s = m.group(0).replace(",", "").replace("，", "").replace("−", "-")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


class Ctx:
    """检查用的交付视图：workspace 下的文件与按文件抽取的文本行（缓存）。"""

    def __init__(self, workspace: Path, lines_of):
        self.workspace = Path(workspace)
        self._lines_of = lines_of
        self._cache: dict[Path, list] = {}
        self.errors: dict[str, str] = {}
        self.files = sorted(p for p in self.workspace.rglob("*")
                            if p.is_file() and not p.name.startswith(("~$", ".")))

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.workspace))

    def select(self, pattern: str | None) -> list[Path]:
        if not pattern:
            return self.files
        return [p for p in self.files if fnmatch.fnmatch(self.rel(p), pattern) or fnmatch.fnmatch(p.name, pattern)]

    def lines(self, p: Path) -> list[str]:
        if p not in self._cache:
            try:
                self._cache[p] = [str(x) for x in self._lines_of(p)]
            except Exception as e:  # 解析失败显式记录在 errors，进 reward_detail
                self._cache[p] = []
                self.errors[self.rel(p)] = f"{type(e).__name__}: {e}"[:300]
        return self._cache[p]


def _match_value(got, chk: dict) -> bool:
    if "equals" in chk:
        return str(got).strip() == str(chk["equals"]).strip()
    try:
        g = float(str(got).replace(",", "").replace("−", "-").rstrip("%"))
    except (TypeError, ValueError):
        return False
    tol = float(chk.get("tolerance", 0))
    return any(abs(g - float(v)) <= tol + 1e-12 for v in [chk["value"], *chk.get("alt_values", [])])


def check_number(ctx: Ctx, chk: dict, negative: bool):
    ctxwords = chk.get("context") or []
    if not ctxwords:
        raise ValueError("number 检查必须给 context（指标、主体、期间等定位词）")
    hits = []
    for p in ctx.select(chk.get("file")):
        for ln in ctx.lines(p):
            if all(w in ln for w in ctxwords) and any(_match_value(n, chk) for n in _nums(ln, chk.get("unit"))):
                hits.append(f"{ctx.rel(p)}：{ln.strip()[:300]}")
    want = f"{chk['value']}{chk.get('unit', '')}（容差 {chk.get('tolerance', 0)}，同行含 {'、'.join(ctxwords)}）"
    if negative:
        return len(hits), "\n".join(hits[:5]) or "无", f"命中 {len(hits)} 处：{want}"
    return (1.0 if hits else 0.0), (hits[0] if hits else "无"), ("找到" if hits else "未找到") + want


def check_regex(ctx: Ctx, chk: dict, negative: bool):
    rx = re.compile(chk["pattern"])
    ctxwords = chk.get("context") or []
    hits = [f"{ctx.rel(p)}：{ln.strip()[:300]}" for p in ctx.select(chk.get("file")) for ln in ctx.lines(p)
            if all(w in ln for w in ctxwords) and rx.search(ln)]
    if negative:
        return len(hits), "\n".join(hits[:5]) or "无", f"匹配 {len(hits)} 处：/{chk['pattern']}/"
    return (1.0 if hits else 0.0), (hits[0] if hits else "无"), f"{'匹配' if hits else '未匹配'} /{chk['pattern']}/"


def check_file_exists(ctx: Ctx, chk: dict, negative: bool):
    got = ctx.select(chk["pattern"])
    need = int(chk.get("min_count", 1))
    ev = "、".join(ctx.rel(p) for p in got[:10]) or "无"
    if negative:
        return len(got), ev, f"存在 {len(got)} 个匹配 {chk['pattern']} 的文件"
    return (1.0 if len(got) >= need else 0.0), ev, f"匹配 {chk['pattern']} 的文件 {len(got)} 个（要求 ≥{need}）"


def _json_path(obj, path: str):
    for part in [x for x in re.split(r"\.(?![^\[]*\])", path) if x]:
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def check_json_value(ctx: Ctx, chk: dict, negative: bool):
    files = ctx.select(chk["file"])
    if not files:
        return 0.0, "无", f"没有 {chk['file']}"
    try:
        got = _json_path(json.loads(files[0].read_text(encoding="utf-8")), chk["path"])
    except Exception as e:
        return 0.0, "无", f"读不到 {chk['file']} 的 {chk['path']}：{type(e).__name__}"
    ok = _match_value(got, chk)
    return (1.0 if ok else 0.0), f"{ctx.rel(files[0])} {chk['path']} = {got!r}", \
        f"期望 {chk.get('equals', chk.get('value'))}（容差 {chk.get('tolerance', 0)}）"


def check_xlsx_cell(ctx: Ctx, chk: dict, negative: bool):
    import openpyxl
    files = [p for p in ctx.select(chk["file"]) if p.suffix.lower() in (".xlsx", ".xlsm")]
    if not files:
        return 0.0, "无", f"没有 {chk['file']}"
    wb = openpyxl.load_workbook(str(files[0]), data_only=True)
    ws = wb[chk["sheet"]] if chk.get("sheet") else wb.worksheets[0]
    if chk.get("cell"):
        coord, got = chk["cell"], ws[chk["cell"]].value
    else:  # 按行标签 + 列标签定位：行标签在 label_col 列（默认 A），列标签在 header_row 行（默认 1）
        hdr = int(chk.get("header_row", 1))
        col = next((c.column for c in ws[hdr] if str(c.value or "").strip() == chk["col_label"]), None)
        lab = chk.get("label_col", "A")
        row = next((c.row for c in ws[lab] if str(c.value or "").strip() == chk["row_label"]), None)
        if col is None or row is None:
            return 0.0, "无", f"找不到行“{chk['row_label']}”或列“{chk['col_label']}”"
        cell = ws.cell(row=row, column=col)
        coord, got = cell.coordinate, cell.value
    if got is None:
        return 0.0, f"{ctx.rel(files[0])} {ws.title}!{coord} 为空", "单元格为空（公式缓存缺失时由判分程序先重算）"
    ok = _match_value(got, chk)
    return (1.0 if ok else 0.0), f"{ctx.rel(files[0])} {ws.title}!{coord} = {got!r}", \
        f"期望 {chk.get('equals', chk.get('value'))}（容差 {chk.get('tolerance', 0)}）"


_CUSTOM = {}


def check_python(ctx: Ctx, chk: dict, negative: bool, task_dir: Path, criterion: dict):
    path = task_dir / chk.get("module", "custom_checks.py")
    if path not in _CUSTOM:
        spec = importlib.util.spec_from_file_location("custom_checks", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CUSTOM[path] = mod
    got = getattr(_CUSTOM[path], chk["function"])(ctx, criterion)
    if isinstance(got, dict):
        return float(got["value"]), str(got.get("evidence", "")), str(got.get("reason", ""))
    return float(got), "", f"{chk['function']} 返回 {got}"


def run(ctx: Ctx, criterion: dict, task_dir: Path):
    chk = criterion["check"]
    neg = criterion["polarity"] == "negative"
    kind = chk["kind"]
    if kind == "python":
        return check_python(ctx, chk, neg, task_dir, criterion)
    return {"number": check_number, "regex": check_regex, "file_exists": check_file_exists,
            "json_value": check_json_value, "xlsx_cell": check_xlsx_cell}[kind](ctx, chk, neg)
