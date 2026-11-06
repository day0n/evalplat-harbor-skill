"""交付文本抽取：把 /app/output 下的文件转成判分可读的文本行。

- docx 按 XML 读取并接受全部修订（docx_xml.py）；doc/rtf 先用 LibreOffice 转 docx；
- pdf 用 pdftotext 版面抽取，按页标注；xlsx 按工作表逐行（公式缺缓存值时先用 LibreOffice 重算）；
- 超长文件按关键词摘取，全部交付有总量上限，截断都在文本里显式标出。
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import docx_xml as dx  # noqa: E402

FILE_FULL = 60000      # 单个文件不超过该字数时全文给判分模型
FILE_EXCERPT = 45000   # 超长文件按关键词摘取的上限
TOTAL_CAP = 180000     # 全部交付文本上限
TEXT_EXTS = {".docx", ".doc", ".pdf", ".xlsx", ".xlsm", ".md", ".txt", ".csv", ".rtf", ".html", ".htm"}



def _pdf_lines(p: Path) -> list:
    r = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=600)
    pages = r.stdout.split("\f")
    out = []
    for i, page in enumerate(pages, 1):
        lines = [ln.rstrip() for ln in page.splitlines() if ln.strip()]
        if lines:
            out.append(f"[第{i}页]")
            out += lines
    return out


def _convert(p: Path, fmt: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="conv-"))
    subprocess.run(["soffice", "--headless", "--convert-to", fmt, "--outdir", str(tmp), str(p)],
                   capture_output=True, timeout=600)
    got = list(tmp.glob(f"*.{fmt}"))
    if not got:
        raise RuntimeError(f"{p.suffix} 转 {fmt} 失败")
    return got[0]


def _formula_without_cache(p: Path) -> bool:
    import openpyxl
    try:
        f = openpyxl.load_workbook(str(p), data_only=False)
        v = openpyxl.load_workbook(str(p), data_only=True)
    except Exception:
        return False
    for ws in f.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("=") and v[ws.title][c.coordinate].value is None:
                    return True
    return False


def lines_of(p: Path) -> list:
    suf = p.suffix.lower()
    if suf == ".pdf":
        return _pdf_lines(p)
    if suf in (".doc", ".rtf"):
        return dx.file_lines(_convert(p, "docx"))
    if suf in (".xlsx", ".xlsm") and _formula_without_cache(p):
        # 公式格没有缓存值（程序写的公式）：用 LibreOffice 重算后再读
        return dx.file_lines(_convert(p, "xlsx"))
    if suf in (".csv", ".html", ".htm"):
        return [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    return dx.file_lines(p)


def excerpt(text: str, keywords: list, cap: int, window=(2500, 4000), window_more=None) -> str:
    """超长文件：保留开头，再按关键词取前后文。命中次数少的关键词优先（细则锚点如“图表6-61”通常只出现一两次），
    各关键词轮流取第 1、2、3……处，合并重叠区间，直到额度用完；输出按原文顺序。
    每个关键词第 1 处取 window（前、后字数），之后各处取 window_more（未设则同 window），让同样额度覆盖更多命中处。"""
    hits = {}
    for kw in dict.fromkeys(k for k in keywords if k):
        ms = [m.span() for m in re.finditer(re.escape(kw), text)]
        if ms:
            hits[kw] = ms
    order = sorted(hits, key=lambda k: len(hits[k]))
    chosen = [(0, min(len(text), 4000))]

    def covered(spans):
        tot, end = 0, -1
        for a, b in sorted(spans):
            if b <= end:
                continue
            tot += b - max(a, end)
            end = b
        return tot

    rank, full = 0, False
    while not full and any(rank < len(hits[k]) for k in order):
        for k in order:
            if rank >= len(hits[k]):
                continue
            a, b = hits[k][rank]
            wb, wa = window if rank == 0 or not window_more else window_more
            span = (max(0, a - wb), min(len(text), b + wa))
            if covered(chosen + [span]) > cap:
                full = True
                break
            chosen.append(span)
        rank += 1
    merged = []
    for a, b in sorted(chosen):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return "\n".join(f"……（第 {a} 字起）\n{text[a:b]}" for a, b in merged)


def collect(ws: Path, keywords: list, limits: dict | None = None) -> tuple[str, list]:
    lim = limits or {}
    file_full = int(lim.get("file_full", FILE_FULL))
    file_excerpt = int(lim.get("file_excerpt", FILE_EXCERPT))
    total_cap = int(lim.get("total", TOTAL_CAP))
    files, parts, total = [], [], 0
    for p in sorted(ws.rglob("*")):
        if not p.is_file() or p.name.startswith(("~$", ".")):
            continue
        rel = str(p.relative_to(ws))
        info = {"path": rel, "bytes": p.stat().st_size}
        if p.suffix.lower() not in TEXT_EXTS:
            info["note"] = "非文本格式，未抽取"
            files.append(info)
            continue
        try:
            text = "\n".join(lines_of(p))
            if p.suffix.lower() == ".pdf":  # 版面抽取的对齐空格只占额度：连续 3 个以上压成 2 个，列间仍可分辨
                text = re.sub(r"[ \t]{3,}", "  ", text)
        except Exception as e:  # 抽取失败如实告诉判分模型（可读性项据此判）
            info["note"] = f"抽取失败：{type(e).__name__}: {e}"[:300]
            files.append(info)
            parts.append(f"===== 文件：{rel}（无法读取：{info['note']}）=====")
            continue
        info["chars"] = len(text)
        if len(text) > file_full:
            text = excerpt(text, keywords, file_excerpt, tuple(lim.get("window", (2500, 4000))),
                           tuple(lim["window_more"]) if lim.get("window_more") else None)
            info["note"] = f"超长，按关键词摘取 {len(text)} 字"
        if total + len(text) > total_cap:
            text = text[: max(0, total_cap - total)] + "\n……（交付文本总量超限，以下截断）"
            info["note"] = (info.get("note", "") + "；总量超限截断").strip("；")
        total += len(text)
        files.append(info)
        parts.append(f"===== 文件：{rel}（共 {info['chars']} 字{'，' + info['note'] if info.get('note') else ''}）=====\n{text}")
    return "\n\n".join(parts), files

