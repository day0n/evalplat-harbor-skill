---
name: harbor-task-authoring
description: Evalplat 平台 Harbor 题包的标准格式（对齐阿里《Finance RL 数据采购标准 v20261030》）：目录结构、task.toml 与交付元数据、instruction.md、Dockerfile、参考解、评分标准 tests/rubric/rubric.json（统一 JSON Schema、逐项判定、程序聚合）、Rubric 设计说明，附可直接复制的样例题包与判分程序。用户提到造题、出题、题包、Harbor 格式、task.toml、rubric、rubric.json、评分细则、评分项、Gold、参考解、判分、Judge 时使用。
---

# Evalplat Harbor 题包格式

样例题包：
- `templates/rubric-judge/`：判分模型按 rubric.json 逐项判定，数值项由程序检查（文档类题用这个）；
- `templates/deterministic/`：全部评分项由程序比对，不调用判分模型。

两个样例共用同一套判分程序 `tests/grader/`，评分标准都写在 `tests/rubric/rubric.json`。复制一份，按下面的格式改。

## 1. 目录结构

交付时按 `tasks/<sector_code>/<task_id>/` 组织，一题一个目录：

```
tasks/<sector_code>/<task_id>/
├── task.toml                         # 题目配置与元数据（必须）
├── instruction.md                    # 题面（必须，作答方看到的全部要求）
├── environment/
│   ├── Dockerfile                    # 作答环境
│   └── input_files/input/...         # 输入材料，作答时位于 /app/input/（只读）
├── solution/
│   ├── solve.sh                      # 参考解脚本
│   └── golden_output/...             # Gold（专家定稿原件），对作答方不可见
└── tests/
    ├── test.sh                       # 判分入口
    ├── grader/                       # 判分程序（沿用样例，不用改）
    └── rubric/
        ├── rubric.json               # 评分标准（必须）
        ├── instruction.md            # 题面副本，与顶层 instruction.md 相同
        ├── Rubric设计说明.md          # 评分维度、判据依据、权重、判分链路、reward 公式、创作与审核记录
        ├── custom_checks.py          # 可选：自定义程序检查
        └── reference/...             # 评卷参考（Gold 副本等），只给判分模型
```

- 作答方只能看到 `instruction.md` 和 `environment/` 里的内容；`solution/`、`tests/` 不可见。
- 阿里目录里的 `data/input_files/` 对应这里的 `environment/input_files/`：Harbor 只把 `environment/` 作为镜像构建上下文，
  放在题包根目录的 `data/` 进不了作答环境。输入文件全部随包交付，不依赖外链。

## 2. task.toml

```toml
schema_version = "1.4"
artifacts = ["/app/output"]

[task]
name = "docrev/fin-xxx-0001"          # org/name：字母、数字和 ._-
version = "1.0.0"                     # 每次改版递增
description = "题号_标题（题型）"

[metadata]
judge_model = "gpt-6.1-sol"           # 平台判分模型；rubric.json 全是 method=code 时删掉这行
task_family = "资产筛选"              # 题型
source_package = "<原始包 ID>"
# 交付元数据（阿里标准要求）；同一行业、职业、工作流的题可统一取值
sector = "金融"                       # 行业部门
sector_code = "FIN-IBABS"             # 交付目录 tasks/<sector_code>/ 用
occupation = "债券承销"               # 职业
workflow = "资产筛选"                 # 任务 / 工作流
skills = ["财务报表分析", "合规核查"]
difficulty = "hard"                   # easy / medium / hard，按第 6 节基准难度实测后填写
query_domain = "资产支持证券"         # Query 领域
user_role = "投行项目组成员"          # 用户角色
output_format = "xlsx"

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
GRADE_JUDGE_PARALLEL = "4"            # 并发批数
GRADE_CALL_TIMEOUT = "1200"
GRADE_JUDGE_BUDGET = "6600"           # 判分总预算（秒），小于 verifier.timeout_sec
GRADE_MAX_OUTPUT_TOKENS = "32000"

[environment]
os = "linux"
build_timeout_sec = 3600.0
network_mode = "no-network"           # 允许查公开信息时写 "public"
cpus = 4                              # 云沙箱最大 4 核
memory_mb = 16384                     # 云沙箱最大 16G，内存/CPU 比 1~4
storage_mb = 10240
```

`[metadata]` 里不要用 `category`、`subcategory`、`collection`：这几个键平台用来定目录。

## 3. instruction.md

题面原文在前，末尾固定加一段环境说明：

```markdown
FIN-XXX-0001

# 标题

（专家题面原文：角色与背景、要做什么、依据哪些材料、交什么、格式要求或"不限文件格式"、能否联网）

---

题包材料在 `/app/input/`（只读），空表为 `input/xxx.xlsx`。
全部交付文件放在 `/app/output/`（当前工作目录为 `/app`）。
```

- 题面要真实、完整，包含角色上下文和任务要求，不用模板批量替换生成。
- 题面里引用的材料路径（如 `input/项目底稿/`）要与 `environment/input_files/input/` 下的实际目录一致。
- 评分项、Gold 位置不写进题面；但每条评分项都要能在题面的显式或合理隐含要求里找到来源。

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

一般只需要改输入材料，Dockerfile 照抄。Gold、rubric 不要放进 `environment/`。

## 5. solution（参考解）

`golden_output/` 放专家定稿原件。`solve.sh` 把它原样拷到 `/app/output/` 并校验哈希：

```bash
#!/bin/bash
set -euo pipefail
mkdir -p /app/output
cp "/solution/golden_output/专家定稿表.xlsx" /app/output/
echo "<SHA-256>  /app/output/专家定稿表.xlsx" | sha256sum -c -
```

Gold 按 rubric.json 判分应接近满分（阿里验收要求 Golden 重复判分均分 ≥ 0.9）。

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

### rubric/rubric.json

一题一个文件，统一 Schema，同批题目使用同一套顶层键。完整样例见 `templates/rubric-judge/tests/rubric/rubric.json`。

```json
{
 "schema": "evalplat-rubric/2",
 "task_id": "FIN-XXX-0001",
 "role": "上市公司财务核查",
 "guidelines": ["等价表述、合理换算均可接受。"],
 "judge": {"batch_size": 10},
 "extraction": {"keywords": ["资产负债率", "负债合计"]},
 "groups": {"R": {"label": "回复", "scale": 1.0}, "M": {"label": "改件", "scale": 1.0}},
 "scoring": {"round": 2},
 "criteria": [
  {
   "id": "R06",
   "description": "DCF估值模型中使用的WACC取值应落在合理区间[10%, 12%]内，越接近得分越高",
   "tag": "内容质量-数值与计算准确性",
   "criterion_type": "Objective",
   "criterion_necessity": "Explicit",
   "type": "gradient",
   "weight": 7.0,
   "method": "llm",
   "polarity": "positive",
   "group": "M",
   "levels": {
    "1": "WACC落在[10%, 12%]区间内",
    "0.75": "WACC偏离合理区间不超过±1%（如9.0%–9.9%或12.1%–13.0%）",
    "0.5": "WACC偏离合理区间±1%–±3%（如7.0%–8.9%或13.1%–15.0%）",
    "0.25": "WACC偏离合理区间±3%–±5%（如5.0%–6.9%或15.1%–17.0%）",
    "0": "WACC完全未给出，或偏离合理区间超过±5%"
   }
  },
  {
   "id": "R17",
   "description": "计算2025年盈利净值为50万美元，相较于2024年盈利净值环比增长20%。",
   "tag": "内容质量-数值与计算准确性",
   "criterion_type": "Objective",
   "criterion_necessity": "Explicit",
   "type": "binary",
   "weight": 3.0,
   "method": "llm",
   "polarity": "positive",
   "group": "M"
  },
  {
   "id": "R18",
   "description": "2025年盈利净值写为50万美元，与“2025”“盈利净值”出现在同一行。",
   "tag": "内容质量-数值与计算准确性",
   "criterion_type": "Objective",
   "criterion_necessity": "Explicit",
   "type": "binary",
   "weight": 2.0,
   "method": "code",
   "polarity": "positive",
   "group": "M",
   "check": {"kind": "number", "value": 50, "unit": "万美元", "context": ["2025", "盈利净值"]}
  }
 ]
}
```

**顶层键**（只能用这些）：

| 键 | 必填 | 含义 |
|---|---|---|
| `schema` | 是 | 固定 `"evalplat-rubric/2"` |
| `task_id` | 是 | 题号 |
| `criteria` | 是 | 评分项列表，正向项至少 6 条 |
| `role` | | 判分模型扮演的阅卷人身份 |
| `guidelines` | | 全题通用的判分口径（等价表述、换算、载体等），逐条一句 |
| `judge` | | `batch_size`：每次交给判分模型的评分项条数（默认 10） |
| `extraction` | | 长文件摘取：`keywords` 定位词，可调 `file_full`、`file_excerpt`、`total` 字数上限 |
| `groups` | | 分组与组折算系数 `{"代号": {"label", "scale"}}`；写了就每条都要有 `group` |
| `scoring` | | `round`：总分保留几位小数 |

**每条评分项的字段**：

| 字段 | 必填 | 取值 |
|---|---|---|
| `id` | 是 | 字母、数字、`_`、`-`，题内唯一 |
| `description` | 是 | 独立、明确、可验证的判据；涉及数字写出具体值（“增长 65%”，不写“出现增长”） |
| `tag` | 是 | 评分维度，取下表之一 |
| `criterion_type` | 是 | `Objective`（可重复验证）/ `Subjective`（专业语义或观感判断） |
| `criterion_necessity` | 是 | `Explicit`（题面明确要求）/ `Implicit`（合理隐含要求） |
| `type` | 是 | `binary`（满足 / 不满足）/ `gradient`（按 `levels` 分档） |
| `weight` | 是 | 正数；正向项为满分分值，负向项为每次命中扣的分 |
| `method` | 是 | `code`（程序检查，写 `check`）/ `llm`（判分模型判定） |
| `polarity` | 是 | `positive`（答对得分）/ `negative`（犯错扣分） |
| `levels` | gradient 必填 | `{"档位值": "判定描述"}`，档位值是 0~1 的数字字符串，必须含 `"1"` 和 `"0"` |
| `check` | code 必填 | 见下方检查类型 |
| `requires` | | 必要前提：所列正向项未满分时，本项记 0 |
| `hurdle` | | `true`：本项未满分则整题 0 分（如交付物缺失） |
| `group` | | 所属组 |
| `max_hits` | | 负向 binary 项：每命中一处扣一次 `weight`，最多计几次（不写为 1） |
| `deduct_from` | | 负向项：`group`（默认，从所属组扣，组分最低 0）/ `total`（从总分扣，如表达质量扣分） |
| `note` | | 给出题人和审核人看的备注，不交给判分模型 |

**评分维度（`tag`）**：

| tag | 检查内容 |
|---|---|
| 指令遵循 | 范围、数量、命名、路径、格式、单位、精度、必须 / 禁止内容 |
| 内容质量-结论正确性 | 最终判断与证据一致，无方向错误、无关键结论遗漏 |
| 内容质量-数值与计算准确性 | 取数、公式、口径、换算、聚合、时间、精度、容差 |
| 内容质量-专业规范 | 行业知识、规则、准则、术语和业务口径 |
| 内容质量-分析与论证质量 | 回答核心问题，有逻辑和证据的归因、比较、洞察 |
| 内容质量-事实忠实性 | 事实、数据、引用可追溯，不编造，跨文件区分主体、版本、时间、口径 |
| 结构与组织 | 章节、层级、顺序、分组与上下文合理 |
| 操作与交付安全 | 不误删、覆盖、破坏无关文件；转换不丢数据、公式、页面 |
| 安全合规 | 隐私、数据安全、版权、法律与业务合规 |
| 超预期贡献 | 其余要求满足后的额外价值（二次核对、指出指令疏漏等） |
| 视觉美感 | 仅对有美观要求的交付物配置 |

**程序检查（`method: "code"` 的 `check`）**：

| kind | 写法 | 判定 |
|---|---|---|
| `number` | `value`、`tolerance`、`context`（同一行必须同时出现的定位词）、可选 `unit`、`file`、`alt_values` | 同一行出现全部定位词，且有数在容差内（写了 `unit` 时数字后须紧跟该单位） |
| `regex` | `pattern`，可选 `context`、`file` | 有一行匹配；负向项按匹配行数计命中 |
| `file_exists` | `pattern`（glob），可选 `min_count` | 交付目录里匹配的文件数 |
| `json_value` | `file`、`path`（如 `a.b.0`）、`value` + `tolerance` 或 `equals` | JSON 取值比对 |
| `xlsx_cell` | `file`、可选 `sheet`；`cell`（如 `B7`）或 `row_label` + `col_label` | 单元格实际值比对（公式缺缓存值时先重算） |
| `python` | `function`，可选 `module`（默认 `custom_checks.py`） | 自定义函数 `f(ctx, criterion)`，返回 0~1 或 `{"value", "evidence", "reason"}`；gradient 的程序检查只能用这种 |

`file` 按交付目录内的相对路径或文件名做 glob 匹配。数值判定必须绑定指标、主体、期间、单位，不能全文搜到数字就判对。

出题时运行校验，输出条数与占比：

```bash
python3 tests/grader/rubric_schema.py tests/rubric/rubric.json
```

### rubric/Rubric设计说明.md

每题一份：评分维度与权重、判据设计依据、判分链路、真实产物读取方式、reward 公式、确定性与 LLM 判据占比、
Gold 来源与 SHA-256、作者与二审人（专业背景）、工时、修订记录与 AI 辅助披露。照样例填写。

### rubric/reference/

放 Gold 副本和评卷参考，与 `solution/golden_output/` 中的原件一致。只给判分模型，不进作答环境。

## 7. Rubric 写法原则

- **原子性**：每条 description 是一个独立、明确、可验证的评分点。
- **独立验证**：不依赖其他内容再判断；涉及数字写明具体值。
- **与题面一致**：来自题面的显式要求或合理隐含要求，不构造伪需求。
- **无重复、无冲突**：不同条目评不同内容，同一错误只在一处失分。
- **粒度合理**：不把一个动作拆成大量无意义小项，也不把多个要求合成一条。
- **覆盖完整**：全部条目共同覆盖题面的主要考察目标。
- **不写空洞条目**：不写“语言流畅”“结构清晰”这类无锚点要求；主观要求转成可观察标准
  （如“PPT 排版美观”改成“单页正文不超过 150 字”）。
- **权重**：核心项权重高；存在性、数值、公式、数量、容差优先用程序检查，专业语义和主观分档交给判分模型。
- **负向项**：只写题面明确禁止或必然导致错误披露的情形；清单内本来要做对的内容错了，按该正向项失分，不再按负向项扣。

## 8. 判分与 reward

判分程序（`tests/grader/rubric_verify.py`）按以下顺序执行，判据定义、证据读取、逐项判定、总分聚合相互分离：

1. 校验 rubric.json，不合规范直接退出、不写 reward。
2. 读取 `/app/output/` 下的真实交付文件（docx 接受修订、pdf 按页、xlsx 读实际值、超长按关键词摘取），
   截断和解析失败都记入明细，不当空答案。
3. `method: "code"` 的项由程序检查。
4. `method: "llm"` 的正向项分批交给判分模型；模型只输出 binary 的 yes/no 或 gradient 的档位键、答卷原文证据和理由，不给分数。
5. 负向项在正向项评完后单独判定，附上已评结果，避免重复扣分。
6. 程序聚合：

```
正向得分 = Σ weight × 档位值（binary 为 0/1；requires 未满足记 0）
扣分     = Σ weight × 命中次数（负向 binary）或 weight × 档位值（负向 gradient）
总分     = max(0, Σ_组 max(0, 组内正向 − 组内扣分) × scale − 总分扣分)；hurdle 未满足则总分为 0
reward   = 总分 ÷ Σ_组（组内正向 weight 之和 × scale）
```

输出 `/logs/verifier/reward.json`（`{"reward": 0~1 的连续分数}`）和 `reward_detail.json`
（逐项判定、档位值、得分、证据、理由、判分模型、各组小计与公式）。判分模型不可用时不写 reward、以非零退出，
平台记“判分出错”，不记 0 分。

## 9. 与 RewardKit 的对应

阿里要求判分器尽量对齐 Harbor + RewardKit；存量自研判分器可保留，但要提供映射说明。本平台题目不联网判分，
判分程序随包交付、`tests/test.sh` 一键运行，对应关系如下（对照 harbor-rewardkit 0.2.4）：

| rubric.json | RewardKit |
|---|---|
| `method: "llm"` 的评分项 | judge TOML 的 `[[criterion]]`（`id`、`description`、`weight`） |
| `type: "binary"` | `type = "binary"` |
| `type: "gradient"` + `levels` | `type = "rubric"` + `levels`（从低到高）；RewardKit 档位按等距取值，rubric.json 的档位值显式写在键上，不等距时以 rubric.json 为准 |
| `method: "code"` + `check` | Python criterion：`file_exists`、`json_value` ≈ `json_path_equals`、`xlsx_cell` ≈ `xlsx_cell_equals`、`number` ≈ `file_contains` 加同行上下文绑定、`python` ≈ 自定义 criterion |
| `polarity: "negative"` | 按扣分处理，相当于 `weighted-sum` 里的负权重项；与 RewardKit 的 `negate`（在加权平均里取 1 − 值）不等价 |
| `hurdle: true` | `required-pass` 聚合中的必过项 |
| `requires` | 无直接对应，由判分程序在聚合前处理 |
| `groups` + `scale` | 两级 `[[reward]]` 的 `weights` |
| reward = 总分 ÷ 满分 | 正向 `weighted-sum` 后按满分归一化 |
| `task.toml` 的 `judge_model` / `JUDGE_*` 环境变量 | `[judge] judge = "<LiteLLM 模型名>"` |

## 10. 换判分模型复验

阿里要求至少 3 个能力相当、不同系列的判分模型（必须含 Qwen3.8-Flash），对同一批固定产物判分，跨模型最大分差 < 0.10。
判分程序支持用环境变量指定任意模型（OpenAI Chat 兼容协议写 `openai`，Responses 写 `responses`）：

```bash
JUDGE_API_KEY=... JUDGE_BASE_URL=https://<网关>/v1 JUDGE_MODEL=qwen3.8-flash JUDGE_API_PROTOCOL=openai \
python3 tests/grader/rubric_verify.py --task tests/rubric --instruction tests/rubric/instruction.md \
  --workspace <固定产物目录> --logs out/qwen3.8-flash
```

每个模型、每份产物各跑一次，比较各自 `reward_detail.json` 的逐项判定和 reward。`GRADE_REASONING_EFFORT` 只对 Responses 协议生效。
平台上的正式判分只用 `task.toml` 里的 `judge_model`。

## 11. 从旧格式（rubric.md + items.json）迁移

旧题包自带旧判分程序，不改也能照常运行；新出的题和交付阿里的题用 rubric.json。迁移时逐条对应：

| 旧写法 | rubric.json |
|---|---|
| 细则表格的一行（编号、分值、通过条件） | 一条 criterion：`id`、`weight`、`description` |
| `all_or_nothing` / 只取全分或零分 | `type: "binary"` |
| 细则写明的部分得分档 | `type: "gradient"` + `levels`，档位值 = 档位分 ÷ 满分；没写明档位的部分分要请专家定档 |
| `requires` | `requires` |
| `groups.scale` | `groups.scale` |
| 清单外错误（每处扣 N 分） | 负向项：`polarity: "negative"`、`weight: N`、`max_hits` |
| L1–L3 表达扣分（0/2/4） | 每项一条负向 gradient：`weight: 4`、`levels` `{"1": 扣 4 分的情形, "0.5": 扣 2 分的情形, "0": 不扣}`、`deduct_from: "total"` |
| `extra.py` 逐行落点 | `method: "code"`，用 `number`、`xlsx_cell` 或 `python` 检查 |
| `rubric.md` 原文 | 可留在 `tests/rubric/source/` 存档，判分不读取；判分口径写进各条 `description` 和 `guidelines` |

## 12. 打包

一题一个文件夹，按 `tasks/<sector_code>/<task_id>/` 放置。文本文件一律 UTF-8，脚本用 LF 换行。
