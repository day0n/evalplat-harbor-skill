"""docx 正文按 XML 直接读取（反馈答复类题目的交付物常带修订痕迹）。

- 只读 word/document.xml，不依赖关系表（个别原件的关系表指向不存在的部件，python-docx 打不开）；
- 计入插入修订（w:ins 内的 w:t），不计删除修订（w:del / w:delText / w:moveFrom），即「接受全部修订」后的文本；
- 段号与源题审核标准的坐标约定一致：body 直接子 w:p 从 1 开始；表号为 body 直接子 w:tbl 从 1 开始。
"""
import re
import zipfile
import xml.etree.ElementTree as ET

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SKIP = {_W + "del", _W + "moveFrom", _W + "delText", _W + "instrText"}


def _text(el) -> str:
    out = []

    def walk(e):
        if e.tag in _SKIP:
            return
        if e.tag == _W + "t" and e.text:
            out.append(e.text)
        elif e.tag in (_W + "tab",):
            out.append("\t")
        elif e.tag in (_W + "br", _W + "cr"):
            out.append(" ")
        for c in e:
            walk(c)

    walk(el)
    return "".join(out)


def _row_deleted(tr) -> bool:
    pr = tr.find(_W + "trPr")
    return pr is not None and pr.find(_W + "del") is not None


def _table(tbl) -> list:
    rows = []
    for tr in tbl.iter(_W + "tr"):
        if _row_deleted(tr):
            continue
        cells = []
        for tc in tr.findall(_W + "tc"):
            cells.append(" ".join(t for t in (_text(p).strip() for p in tc.iter(_W + "p")) if t))
        rows.append(cells)
    return rows


def docx_blocks(path) -> list:
    """按正文顺序返回 [("p", 段号, 文本) | ("t", 表号, 行列表)]。w:sdt 内容展开。"""
    with zipfile.ZipFile(str(path)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(_W + "body")
    blocks, pi, ti = [], 0, 0

    def visit(children):
        nonlocal pi, ti
        for ch in children:
            if ch.tag == _W + "p":
                pi += 1
                blocks.append(("p", pi, _text(ch)))
            elif ch.tag == _W + "tbl":
                ti += 1
                blocks.append(("t", ti, _table(ch)))
            elif ch.tag == _W + "sdt":
                content = ch.find(_W + "sdtContent")
                if content is not None:
                    visit(list(content))

    visit(list(body))
    return blocks


def docx_lines(path) -> list:
    """判分片段：每段一行，每个表格行一行（单元格以 | 连接），空行去掉。"""
    out = []
    for kind, _, v in docx_blocks(path):
        if kind == "p":
            if v.strip():
                out.append(v.strip())
        else:
            for row in v:
                line = " | ".join(c for c in row)
                if line.replace("|", "").strip():
                    out.append(line)
    return out


def docx_tables(path) -> list:
    return [v for kind, _, v in docx_blocks(path) if kind == "t"]


def docx_has_revisions(path) -> bool:
    with zipfile.ZipFile(str(path)) as z:
        xml = z.read("word/document.xml")
    return b"<w:ins " in xml or b"<w:del " in xml


def xlsx_lines(path, max_rows: int = 2000) -> list:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append(f"【工作表 {ws.title}】")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                out.append("【已截断】")
                break
            vals = ["" if v is None else str(v) for v in row]
            if any(v.strip() for v in vals):
                out.append(" | ".join(vals).rstrip(" |"))
    return out


def file_lines(path) -> list:
    p = str(path).lower()
    if p.endswith(".docx"):
        return docx_lines(path)
    if p.endswith((".xlsx", ".xlsm")):
        return xlsx_lines(path)
    if p.endswith((".md", ".txt")):
        return [l for l in open(path, encoding="utf-8", errors="replace").read().splitlines() if l.strip()]
    return []


def find_files(ws, include: list, exts=(".docx",), exclude: list = (), include_any: list = ()) -> list:
    """输出目录（含子目录）里文件名同时包含 include 各词、含 include_any 中任一词（给了时）、
    且不含 exclude 各词的文件，按路径排序。"""
    from pathlib import Path
    hits = []
    for p in sorted(Path(ws).rglob("*")):
        if not p.is_file() or p.name.startswith(("~$", ".")) or p.suffix.lower() not in exts:
            continue
        if (all(k in p.name for k in include) and not any(k in p.name for k in exclude)
                and (not include_any or any(k in p.name for k in include_any))):
            hits.append(p)
    return hits
