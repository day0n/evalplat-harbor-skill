"""rubric.json 的读取与校验（判分前必过；出题时也可单独运行：python3 rubric_schema.py tests/rubric/rubric.json）。

每条评分项的必填字段沿用阿里《Finance RL 数据采购标准》的 rubric.json 示例
（id、description、tag、criterion_type、criterion_necessity、type、weight，gradient 另有 levels），
本平台另加必填的 method（code / llm）与 polarity（positive / negative）。
校验不过说明题包写错了：直接报错退出，不写 reward。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA = "evalplat-rubric/2"

TOP_REQUIRED = ("schema", "task_id", "criteria")
TOP_OPTIONAL = ("role", "guidelines", "judge", "extraction", "groups", "scoring")

ITEM_REQUIRED = ("id", "description", "tag", "criterion_type", "criterion_necessity",
                 "type", "weight", "method", "polarity")
ITEM_OPTIONAL = ("levels", "check", "requires", "hurdle", "group", "max_hits", "deduct_from", "note")

# 评分维度（阿里标准“评分维度参考”），tag 必须取其一
TAGS = (
    "指令遵循",
    "内容质量-结论正确性",
    "内容质量-数值与计算准确性",
    "内容质量-专业规范",
    "内容质量-分析与论证质量",
    "内容质量-事实忠实性",
    "结构与组织",
    "操作与交付安全",
    "安全合规",
    "超预期贡献",
    "视觉美感",
)
CHECK_KINDS = ("number", "regex", "file_exists", "json_value", "xlsx_cell", "python")
MIN_CRITERIA = 6


class RubricError(ValueError):
    """题包的 rubric.json 不合规范。"""


def _level_keys(levels: dict, where: str) -> list[float]:
    if not isinstance(levels, dict) or len(levels) < 2:
        raise RubricError(f"{where}：gradient 必须有 levels，且至少两档")
    vals = []
    for k, desc in levels.items():
        try:
            v = float(k)
        except ValueError:
            raise RubricError(f"{where}：levels 的键必须是 0~1 的数字字符串，如 \"0.5\"，实际 {k!r}") from None
        if not 0.0 <= v <= 1.0:
            raise RubricError(f"{where}：levels 的键 {k!r} 超出 0~1")
        if not isinstance(desc, str) or not desc.strip():
            raise RubricError(f"{where}：档位 {k!r} 缺少判定描述")
        vals.append(v)
    if 1.0 not in vals or 0.0 not in vals:
        raise RubricError(f"{where}：levels 必须包含 \"1\"（满档）与 \"0\"（零档）")
    return sorted(vals)


def validate(rub: dict) -> dict:
    if not isinstance(rub, dict):
        raise RubricError("rubric.json 顶层必须是对象")
    unknown = set(rub) - set(TOP_REQUIRED) - set(TOP_OPTIONAL)
    if unknown:
        raise RubricError(f"rubric.json 顶层有未定义的键：{sorted(unknown)}（同批题目必须用同一套顶层键）")
    for k in TOP_REQUIRED:
        if k not in rub:
            raise RubricError(f"rubric.json 缺少顶层键 {k}")
    if rub["schema"] != SCHEMA:
        raise RubricError(f"schema 必须是 {SCHEMA!r}，实际 {rub['schema']!r}")
    groups = rub.get("groups") or {}
    for g, cfg in groups.items():
        if not isinstance(cfg, dict) or not isinstance(cfg.get("label", ""), str):
            raise RubricError(f"groups.{g} 必须是对象（label、scale）")
        if float(cfg.get("scale", 1.0)) <= 0:
            raise RubricError(f"groups.{g}.scale 必须大于 0")

    items = rub["criteria"]
    if not isinstance(items, list) or not items:
        raise RubricError("criteria 必须是非空列表")
    positives = [c for c in items if isinstance(c, dict) and c.get("polarity") == "positive"]
    if len(positives) < MIN_CRITERIA:
        raise RubricError(f"正向评分项只有 {len(positives)} 条，阿里标准要求每题至少 {MIN_CRITERIA} 条")

    seen = set()
    for n, c in enumerate(items, 1):
        where = f"criteria 第 {n} 条（{c.get('id', '?') if isinstance(c, dict) else '?'}）"
        if not isinstance(c, dict):
            raise RubricError(f"{where} 必须是对象")
        miss = [k for k in ITEM_REQUIRED if k not in c]
        if miss:
            raise RubricError(f"{where} 缺少字段 {miss}")
        extra = set(c) - set(ITEM_REQUIRED) - set(ITEM_OPTIONAL)
        if extra:
            raise RubricError(f"{where} 有未定义的字段 {sorted(extra)}")
        cid = c["id"]
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cid):
            raise RubricError(f"{where}：id 只能用字母、数字、_ 和 -，不超过 64 字符")
        if cid in seen:
            raise RubricError(f"{where}：id {cid} 重复")
        seen.add(cid)
        if not isinstance(c["description"], str) or len(c["description"].strip()) < 4:
            raise RubricError(f"{where}：description 要写成独立、可验证的完整判据")
        if c["tag"] not in TAGS:
            raise RubricError(f"{where}：tag {c['tag']!r} 不在评分维度表内：{'、'.join(TAGS)}")
        if c["criterion_type"] not in ("Objective", "Subjective"):
            raise RubricError(f"{where}：criterion_type 只能是 Objective 或 Subjective")
        if c["criterion_necessity"] not in ("Explicit", "Implicit"):
            raise RubricError(f"{where}：criterion_necessity 只能是 Explicit 或 Implicit")
        if c["type"] not in ("binary", "gradient"):
            raise RubricError(f"{where}：type 只能是 binary 或 gradient")
        if c["polarity"] not in ("positive", "negative"):
            raise RubricError(f"{where}：polarity 只能是 positive 或 negative")
        if c["method"] not in ("code", "llm"):
            raise RubricError(f"{where}：method 只能是 code 或 llm")
        try:
            w = float(c["weight"])
        except (TypeError, ValueError):
            raise RubricError(f"{where}：weight 必须是数字") from None
        if not w > 0:
            raise RubricError(f"{where}：weight 必须大于 0（负向项也写正数，表示命中时扣的分）")
        if c["type"] == "gradient":
            _level_keys(c.get("levels"), where)
        elif "levels" in c:
            raise RubricError(f"{where}：binary 不写 levels")
        if c["method"] == "code":
            chk = c.get("check")
            if not isinstance(chk, dict) or chk.get("kind") not in CHECK_KINDS:
                raise RubricError(f"{where}：method=code 必须有 check，kind 取 {CHECK_KINDS}")
            if c["type"] == "gradient" and chk["kind"] != "python":
                raise RubricError(f"{where}：程序判的 gradient 项只能用 python 检查（返回档位）")
        elif "check" in c:
            raise RubricError(f"{where}：method=llm 不写 check")
        if "max_hits" in c:
            if c["polarity"] != "negative" or c["type"] != "binary":
                raise RubricError(f"{where}：max_hits 只用于 binary 负向项（每命中一处扣一次 weight）")
            if not isinstance(c["max_hits"], int) or c["max_hits"] < 1:
                raise RubricError(f"{where}：max_hits 必须是正整数")
        if c["polarity"] == "negative" and (c.get("requires") or c.get("hurdle")):
            raise RubricError(f"{where}：负向项不设 requires / hurdle")
        if c.get("deduct_from", "group") not in ("group", "total"):
            raise RubricError(f"{where}：deduct_from 只能是 group 或 total")
        if "deduct_from" in c and c["polarity"] != "negative":
            raise RubricError(f"{where}：deduct_from 只用于负向项")
        g = c.get("group")
        if groups and g not in groups:
            raise RubricError(f"{where}：group {g!r} 未在顶层 groups 中定义")
        if not groups and g is not None:
            raise RubricError(f"{where}：写了 group 就要在顶层 groups 中定义")
    for c in items:
        for need in c.get("requires") or []:
            if need not in seen:
                raise RubricError(f"{c['id']}：requires 引用了不存在的 {need}")
            dep = next(x for x in items if x["id"] == need)
            if dep["polarity"] != "positive":
                raise RubricError(f"{c['id']}：requires 只能引用正向项")
    return rub


def load(path: Path) -> dict:
    try:
        rub = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RubricError(f"rubric.json 不是合法 JSON：{e}") from None
    return validate(rub)


def summary(rub: dict) -> dict:
    """交付报告“Rubric 设计说明”要的条数与加权占比。"""
    items = rub["criteria"]
    pos = [c for c in items if c["polarity"] == "positive"]
    wsum = sum(float(c["weight"]) for c in pos) or 1.0

    def share(pred):
        sel = [c for c in pos if pred(c)]
        return {"count": len(sel), "count_ratio": round(len(sel) / len(pos), 4),
                "weight_ratio": round(sum(float(c["weight"]) for c in sel) / wsum, 4)}

    return {
        "criteria": len(items), "positive": len(pos), "negative": len(items) - len(pos),
        "code": share(lambda c: c["method"] == "code"),
        "llm": share(lambda c: c["method"] == "llm"),
        "objective": share(lambda c: c["criterion_type"] == "Objective"),
        "explicit": share(lambda c: c["criterion_necessity"] == "Explicit"),
        "by_tag": {t: share(lambda c, t=t: c["tag"] == t) for t in sorted({c["tag"] for c in pos})},
    }


if __name__ == "__main__":
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/rubric/rubric.json")
    try:
        r = load(p)
    except RubricError as e:
        print(f"不合规范：{e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(summary(r), ensure_ascii=False, indent=1))
