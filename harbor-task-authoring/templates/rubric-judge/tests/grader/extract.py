"""交付文本抽取：把 /app/output 下的文件全部转成判分可读的文本，不摘取、不截断。

- docx 按 XML 读取并接受全部修订（docx_xml.py）；doc/rtf 先用 LibreOffice 转 docx；
- pdf 用 pdftotext 版面抽取，按页标注；抽不出文字的页（扫描件、图片或空白页）逐页记下并告诉判分模型；
- xlsx 按工作表逐行读全部行（公式缺缓存值时先用 LibreOffice 重算）；
- 同一文件的多种格式（同目录同名不同扩展名）只送一份（docx 优先），其余格式比对文字是否一致后写进覆盖记录；
- 全文超过单次送判量时由 make_chunks 按行完整切段，各段拼回去必须与原文逐字相同；
- check_coverage：能抽出的内容有任何一处没送到判分模型就抛 CoverageError（上层不写 reward）。
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import docx_xml as dx  # noqa: E402

TEXT_EXTS = {".docx", ".doc", ".pdf", ".xlsx", ".xlsm", ".md", ".txt", ".csv", ".rtf", ".html", ".htm"}
# 同一文件多种格式时送判哪一份：docx 接受全部修订、表格按行，最完整；PDF 版面抽取次之
FORMAT_ORDER = [".docx", ".doc", ".rtf", ".pdf", ".xlsx", ".xlsm", ".md", ".txt", ".html", ".htm", ".csv"]
SAME_THRESHOLD = 0.9  # 两种格式文字互相覆盖都不低于该比例时视为同一内容


class CoverageError(Exception):
    """有能抽取的内容没有送到判分模型——上层不写 reward，按判分出错处理。"""


# ---------------- 文本抽取 ----------------
PDF_BLANK: dict = {}  # PDF 路径 → (总页数, 抽不出文字的页号列表)
_MEANINGFUL = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def _pdf_lines(p: Path) -> list:
    r = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=600)
    pages = r.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    out, blank = [], []
    for i, page in enumerate(pages, 1):
        lines = [ln.rstrip() for ln in page.splitlines() if ln.strip()]
        if len(_MEANINGFUL.findall(page)) < 10:
            blank.append(i)
        if lines:
            out.append(f"[第{i}页]")
            out += lines
    PDF_BLANK[str(p)] = (len(pages), blank)
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


def _lines_of(p: Path) -> list:
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


_LINES_CACHE: dict = {}
_LINES_LOCK = threading.Lock()


def lines_of(p: Path) -> list:
    """按文件抽取文本行（结果缓存：同一文件在逐项评分、落点核对、改动比对、扣分复核中只抽一次）。"""
    p = Path(p)
    st = p.stat()
    key = (str(p.resolve()), st.st_mtime_ns, st.st_size)
    with _LINES_LOCK:
        if key in _LINES_CACHE:
            return list(_LINES_CACHE[key])
    got = _lines_of(p)
    with _LINES_LOCK:
        _LINES_CACHE[key] = got
    return list(got)


def _ranges(nums: list) -> str:
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}–{prev}")
            start = prev = n
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}–{prev}")
    return "、".join(out)


def _norm(s: str) -> str:
    return "".join(_MEANINGFUL.findall(s))


def _contained(a: str, b: str, k: int = 12, step: int = 5) -> float:
    """b 的文字有多大比例能在 a 中找到（按 k 字片段抽样比对，只看汉字、字母、数字）。"""
    na, nb = _norm(a), _norm(b)
    if not nb:
        return 1.0
    if len(nb) < k or len(na) < k:
        return 1.0 if nb in na else 0.0
    sa = {hash(na[i:i + k]) for i in range(len(na) - k + 1)}
    idx = range(0, len(nb) - k + 1, step)
    return sum(1 for i in idx if hash(nb[i:i + k]) in sa) / len(idx)


def collect(ws: Path) -> tuple[list, list, dict]:
    """返回 (送判文件 [{path, text, chars, note}], 文件清单 [info], 覆盖记录)。全文，不摘取、不截断。"""
    files, docs = [], []
    cov = {"files": [], "unsent_formats": [], "not_extracted": [], "blank_pages": []}
    groups: dict = {}
    for p in sorted(ws.rglob("*")):
        if not p.is_file() or p.name.startswith(("~$", ".")):
            continue
        rel = str(p.relative_to(ws))
        if p.suffix.lower() not in TEXT_EXTS:
            files.append({"path": rel, "bytes": p.stat().st_size, "note": "非文本格式，未抽取"})
            cov["not_extracted"].append({"path": rel, "reason": "非文本格式"})
            continue
        groups.setdefault((str(p.parent), p.stem), []).append(p)

    for _, group in sorted(groups.items()):
        group.sort(key=lambda q: FORMAT_ORDER.index(q.suffix.lower()) if q.suffix.lower() in FORMAT_ORDER else 99)
        texts = {}
        for q in group:
            try:
                t = "\n".join(lines_of(q))
                if q.suffix.lower() == ".pdf":  # 版面抽取的对齐空格：连续 3 个以上压成 2 个，列间仍可分辨，文字不变
                    t = re.sub(r"[ \t]{3,}", "  ", t)
                texts[q] = (t, None)
            except Exception as e:  # 抽取失败如实告诉判分模型（可读性项据此判）
                texts[q] = (None, f"抽取失败：{type(e).__name__}: {e}"[:300])
        # 送判哪一份：按格式优先级取第一份抽得出文字的；都抽不出时取第一份如实标注
        chosen = next((q for q in group if texts[q][0] and texts[q][0].strip()), group[0])
        for q in group:
            rel = str(q.relative_to(ws))
            t, err = texts[q]
            info = {"path": rel, "bytes": q.stat().st_size}
            notes = []
            if q.suffix.lower() == ".pdf" and str(q) in PDF_BLANK:
                n_pages, blank = PDF_BLANK[str(q)]
                info["pages"] = n_pages
                if blank:
                    info["blank_pages"] = _ranges(blank)
                    notes.append(f"共 {n_pages} 页，其中第 {_ranges(blank)} 页抽不出文字（扫描件、图片或空白页），阅卷时看不到这些页")
            if q is chosen:
                if err:
                    info["note"] = err
                    files.append(info)
                    cov["not_extracted"].append({"path": rel, "reason": err})
                    docs.append({"path": rel, "text": "", "chars": 0, "note": f"无法读取：{err}"})
                    continue
                info["chars"] = len(t)
                if not t.strip():
                    notes.append("抽不出任何文字")
                    cov["not_extracted"].append({"path": rel, "reason": "抽不出任何文字"})
                if info.get("blank_pages"):
                    cov["blank_pages"].append({"path": rel, "pages": info["pages"], "blank": info["blank_pages"]})
                others = [x for x in group if x is not q]
                if others:
                    notes.append("同名的 " + "、".join(x.suffix for x in others) + " 未重复送判，见各自说明")
                info["note"] = "；".join(notes)
                files.append(info)
                docs.append({"path": rel, "text": t, "chars": len(t), "note": info["note"]})
                continue
            # 未送判的同名其他格式：比对文字是否与送判那份一致
            ct = texts[chosen][0] or ""
            if err or not (t or "").strip():
                verdict = f"与《{chosen.name}》同名；本格式{err or '抽不出文字'}，未送判"
                same = None
            else:
                a, b = _contained(ct, t), _contained(t, ct)
                same = a >= SAME_THRESHOLD and b >= SAME_THRESHOLD
                verdict = (f"与《{chosen.name}》同名，文字{'一致' if same else '不一致'}"
                           f"（本文件 {a:.0%} 的文字能在送判那份中找到，送判那份 {b:.0%} 的文字能在本文件中找到），"
                           f"未重复送判，按《{chosen.name}》判")
            info["chars"] = len(t or "")
            info["note"] = "；".join(notes + [verdict])
            files.append(info)
            cov["unsent_formats"].append({"path": rel, "judged_as": str(chosen.relative_to(ws)), "same": same,
                                          "note": verdict})
    return docs, files, cov


def render_docs(docs: list) -> str:
    return "\n\n".join(f"===== 文件：{d['path']}（共 {d['chars']} 字{'；' + d['note'] if d.get('note') else ''}）=====\n{d['text']}"
                       for d in docs)


def make_chunks(docs: list, size: int) -> tuple[list, dict]:
    """按行把全部送判文件切成每段不超过 size 字的若干段（接近上限时优先在 PDF 页首处切）；返回 (各段文字, {文件: 已送字数})。
    每个文件各段拼回去必须与原文逐字相同，否则抛 CoverageError。"""
    half = max(1000, size // 2)
    chunks, cur, cur_len = [], [], 0
    for d in docs:
        units = []
        for ln in d["text"].splitlines(keepends=True):
            while len(ln) > half:  # 超长单行按字数切开（极少见），拼回去仍等于原行
                units.append(ln[:half])
                ln = ln[half:]
            if ln:
                units.append(ln)
        seg, seg_start, pos = [], 0, 0
        for u in units:
            soft = cur_len > size * 0.85 and re.fullmatch(r"\[第\d+页\]\n?", u)
            if (seg or cur) and (cur_len + len(u) > size or soft):
                if seg:
                    cur.append((d, seg_start, "".join(seg)))
                chunks.append(cur)
                cur, cur_len, seg, seg_start = [], 0, [], pos
            seg.append(u)
            cur_len += len(u)
            pos += len(u)
        if seg:
            cur.append((d, seg_start, "".join(seg)))
            cur_len += 300  # 文件标题行
    if cur:
        chunks.append(cur)
    pieces: dict = {d["path"]: [] for d in docs}
    out = []
    for parts in chunks:
        body = []
        for d, start, text in parts:
            pieces[d["path"]].append(text)
            pages = re.findall(r"\[第(\d+)页\]", text)
            where = f"第 {start + 1}–{start + len(text)} 字" + (f"，约第 {pages[0]}–{pages[-1]} 页" if pages else "")
            body.append(f"===== 文件：{d['path']}（全文共 {d['chars']} 字；本段为{where}"
                        f"{'；' + d['note'] if d.get('note') else ''}）=====\n{text.rstrip(chr(10))}")
        out.append("\n\n".join(body))
    sent = {}
    for d in docs:
        joined = "".join(pieces[d["path"]])
        if joined != d["text"]:
            raise CoverageError(f"{d['path']} 分段后拼不回原文（{len(joined)} / {d['chars']} 字）")
        sent[d["path"]] = len(joined)
    return out, sent


def check_coverage(cov: dict) -> str:
    """能抽出的内容必须全部送到判分模型；否则抛 CoverageError（不出分）。返回一行覆盖摘要。"""
    short = [f"{f['path']}（{f['sent_chars']}/{f['chars']} 字）" for f in cov["files"] if f["sent_chars"] != f["chars"]]
    d = cov.get("diff")
    if d is not None and d.get("sent_entries") != d.get("entries"):
        short.append(f"改动比对（{d.get('sent_entries')}/{d.get('entries')} 条）")
    cov["complete"] = not short
    if short:
        raise CoverageError("以下内容没有完整送判：" + "；".join(short))
    return ("送判覆盖：全部可抽取内容已送判"
            + (f"；未重复送判的同名格式 {len(cov['unsent_formats'])} 个" if cov["unsent_formats"] else "")
            + (f"；抽不出文字 {len(cov['not_extracted'])} 个文件" if cov["not_extracted"] else "")
            + (f"；含抽不出文字页的 PDF {len(cov['blank_pages'])} 个" if cov["blank_pages"] else ""))
