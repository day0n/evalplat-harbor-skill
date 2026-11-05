---
name: harbor-task-authoring
description: Evalplat 平台 Harbor 题包的标准格式：目录结构、task.toml、instruction.md、Dockerfile、参考解、评分细则 rubric.md 与 items.json 的写法，附可直接复制的样例题包。用户提到造题、出题、题包、Harbor 格式、task.toml、rubric、评分细则、Gold、参考解时使用。
---

# Evalplat Harbor 题包格式

样例题包在 `templates/rubric-judge/`（判分模型按评分细则打分，文档类题用这个），
纯数值、可程序比对的题参考 `templates/deterministic/`。复制一份，按下面的格式改。

## 1. 目录结构

```
<题号>/
├── task.toml                         # 题目配置
├── instruction.md                    # 题面（作答方看到的全部要求）
├── environment/
│   ├── Dockerfile                    # 作答环境
│   └── input_files/input/...         # 输入材料，作答时位于 /app/input/（只读）
├── solution/
│   ├── solve.sh                      # 参考解脚本
│   └── golden_output/...             # Gold（专家定稿原件）
└── tests/
    ├── test.sh                       # 判分入口
    ├── grader/                       # 判分程序（沿用样例，不用改）
    └── rubric/
        ├── rubric.md                 # 评分细则原文
        ├── items.json                # 评分项登记
        ├── instruction.md            # 题面副本，与顶层 instruction.md 相同
        ├── 判分说明.md               # 细则与程序的对应说明
        └── reference/...             # 评卷参考（Gold 副本等），只给判分模型
```

作答方只能看到 `instruction.md` 和 `environment/` 里的内容；`solution/`、`tests/` 不可见。

## 2. task.toml

```toml
schema_version = "1.4"
artifacts = ["/app/output"]

[task]
name = "docrev/fin-xxx-0001"          # org/name：字母、数字和 ._-
version = "1.0.0"                     # 每次改版递增
description = "题号_标题（题型）"

[metadata]
judge_model = "gpt-6.1-sol"           # 判分模型；程序判分的题删掉这行
task_family = "资产筛选"              # 题型
source_package = "<原始包 ID>"

[[metadata.deliverables]]
path = "/app/output/"
required = true
desc = "交付物说明"

[agent]
timeout_sec = 14400.0                 # 作答时限（秒）

[verifier]
timeout_sec = 7200.0                  # 判分时限（秒）
user = "root"
environment_mode = "separate"

[verifier.env]
GRADE_REASONING_EFFORT = "max"        # 判分模型思考强度
GRADE_JUDGE_PARALLEL = "4"
GRADE_CALL_TIMEOUT = "1200"
GRADE_JUDGE_BUDGET = "6600"           # 判分总预算（秒），小于 verifier.timeout_sec
GRADE_MAX_OUTPUT_TOKENS = "32000"

[environment]
os = "linux"
build_timeout_sec = 3600.0
network_mode = "no-network"           # 允许查公开信息时写 "public"
cpus = 4                              # 最大 4 核
memory_mb = 16384                     # 最大 16G
storage_mb = 10240
```

## 3. instruction.md

题面原文在前，末尾固定加一段环境说明：

```markdown
FIN-XXX-0001

# 标题

（专家题面原文：要做什么、依据哪些材料、交什么、格式要求或"不限文件格式"、能否联网）

---

题包材料在 `/app/input/`（只读），空表为 `input/xxx.xlsx`。
全部交付文件放在 `/app/output/`（当前工作目录为 `/app`）。
```

题面里引用的材料路径（如 `input/项目底稿/`）要与 `environment/input_files/input/` 下的实际目录一致。
评分目标、Gold 位置不写进题面。

## 4. environment/Dockerfile

```dockerfile
FROM python:3.12-slim

RUN useradd -m -u 1000 agent

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates bash jq ripgrep unzip poppler-utils \
        libreoffice-writer libreoffice-calc \
        fonts-noto-cjk fonts-arphic-ukai fonts-arphic-uming \
        tesseract-ocr tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        markitdown openpyxl pandas python-docx python-pptx pypdf pdfplumber pymupdf PyYAML chardet pytesseract pillow

COPY input_files/ /app/
RUN chown -R root:root /app && chmod -R a-w /app \
    && mkdir -p /app/output && chown agent:agent /app/output && chmod 755 /app/output
WORKDIR /app
```

一般只需要改输入材料，Dockerfile 照抄。Gold、评分细则不要放进 `environment/`。

## 5. solution（参考解）

`golden_output/` 放专家定稿原件。`solve.sh` 把它原样拷到 `/app/output/` 并校验哈希：

```bash
#!/bin/bash
set -euo pipefail
mkdir -p /app/output
cp "/solution/golden_output/专家定稿表.xlsx" /app/output/
echo "<SHA-256>  /app/output/专家定稿表.xlsx" | sha256sum -c -
```

## 6. tests（判分）

### test.sh

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
python3 /tests/grader/rubric_verify.py \
  --task /tests/rubric \
  --instruction /tests/rubric/instruction.md \
  --workspace /app/output \
  --logs /logs/verifier
```

### rubric/rubric.md

专家评分细则原文。建议结构：

```markdown
# 题号 评分细则

## 得分判法

从 0 分起按下列独立行累加。没有明列部分档的行只取全分或零分。

| 编号 | 分值 | 通过条件 | 必要前提 |
|---|---|---|---|
| R1 | 30 | 写出 2025 年末资产负债率 65.00%（绝对误差 0.01 个百分点），注明取数来源 | — |
| R2 | 40 | 明确结论"超过 60%"；只写"待核"不得分 | R1 |

## 额外错误

- 编造资料中没有的数据：每处扣 5 分，最低 0 分；同一事实只扣一次。

## 总分

各行得分之和减额外错误扣分，最低 0，四舍五入至两位小数，满分 100。
```

数值项写明标准值、单位、容差。

### rubric/items.json

把细则里的评分项逐项登记，分值合计等于 `full`：

```json
{
 "source": "评分细则（原文见 rubric.md）",
 "full": 100.0,
 "role": "上市公司财务核查",
 "groups": {
  "S": {"label": "核查", "scale": 1.0, "business": true}
 },
 "items": [
  {"id": "R1", "max": 30, "group": "S", "title": "2025 年末资产负债率"},
  {"id": "R2", "max": 40, "group": "S", "title": "结论", "requires": ["R1"]}
 ],
 "batches": [["R1", "R2"]],
 "keywords": ["资产负债率", "负债合计"],
 "L": false,
 "round": 2,
 "all_or_nothing": true
}
```

| 字段 | 含义 |
|---|---|
| `full` | 满分 |
| `role` | 判分模型扮演的阅卷人身份 |
| `groups` | 分组：`label` 名称、`scale` 组折算系数、`business` 是否业务分 |
| `items` | 评分项：`id`、`max` 分值、`group`、`title`；`requires` 必要前提（可选）|
| `batches` | 分批交给判分模型评的评分项 ID |
| `keywords` | 长文件摘取用的关键词（表名、科目名、定位词）|
| `L` | 是否有 L1–L3 表达质量扣分 |
| `round` | 总分保留几位小数 |
| `all_or_nothing` | 细则规定每行只取全分或零分时写 `true` |
| `no_deduct` | 细则不设额外扣分时写 `true` |
| `deduct_group` | 额外扣分扣自哪一组 |
| `deduct_note` | 给判分模型的扣分补充说明（不进题面）|
| `gold_target` | Gold 原件中的评分目标位置，如 `{"file": "定稿表.xlsx", "sheet": "Sheet1", "row": 7}` |

### rubric/reference/

放 Gold 副本和评卷参考，与 `solution/golden_output/` 中的原件一致。

### rubric/判分说明.md

写明 Gold 来源和 SHA-256，以及一张"细则内容 → items.json 登记"的对照表，见样例。

## 7. 程序判分的题

不用判分模型时，`tests/test.sh` 直接比对答案，写 `/logs/verifier/reward.json`，分数在 0~1：

```json
{"reward": 1.0}
```

完整写法见 `templates/deterministic/`。

## 8. 打包

一题一个文件夹、一个 zip，按题号命名（如 `FIN-IBABS-ASV-0001-S09.zip`）。文本文件一律 UTF-8，脚本用 LF 换行。
