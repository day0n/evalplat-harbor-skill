---
name: harbor-task-authoring
description: 在 Evalplat 评测平台上按 Harbor 格式造题：把专家原始包（题面、输入材料、Gold/参考成果、文字评分细则）转成可上传的 Harbor 题包，写 task.toml、instruction.md、Dockerfile、判分程序（确定性脚本或判分模型按 rubric 逐项打分）、参考解，做本地预检与 evalplat try 回测，交专家确认后再上传。用户提到造题、出题、题包、Harbor、task.toml、rubric、评分细则、Gold、参考解、回测、evalplat check/try/upload、专家原始包转换时使用。
---

# Evalplat Harbor 造题

本 skill 面向两类人：**出题专家**（懂业务、出题面和评分细则）和**帮专家落地的工程同学或 Claude**。
目标：做出一个"专家认可、平台能验收、判分可信"的 Harbor 题包。

所有内容来自平台代码（`packages/task_types/.../harbor/`）和 2026-10~11 月金融题的实际造题过程。
细节按需读 `references/`：

| 文件 | 什么时候读 |
|---|---|
| `references/format.md` | 写目录、task.toml、判分协议、平台限制、CLI 命令时 |
| `references/rubric.md` | 写评分细则、items.json、判分程序时 |
| `references/backtest.md` | 回测参考解/空卷/错例，准备交付与验收时 |
| `references/pitfalls.md` | 动手前通读一遍；排查低分或误判时 |
| `references/checklist.md` | 交给专家确认前、上传前逐条打勾 |

模板在 `templates/`：`rubric-judge/`（判分模型按专家细则打分，金融文档类题的默认选择）、`deterministic/`（程序直接比对答案）。
预检脚本：`python3 scripts/check_package.py <题包目录>`（只用标准库，Python 3.11+）。

---

## 红线（任何时候都不能破）

1. **评分细则原文不变形。** 专家的 rubric 原样放进 `tests/rubric/rubric.md`；程序只"登记"细则写明的 ID、分值、前提、扣分规则，不自己发明条目、不改写、不合并、不"浓缩"。需要改细则时，让专家改，或者把改动列出来请专家逐条确认。
2. **题面、标准答案、考点、解题思路由专家写或确认。** AI 改过的地方要单独列出、专家逐项认可。不要把 AI 生成的规则当成"专家原始规则"交出去。
3. **以最新原始包为准。** 原始包有新版时，按文件索引的 SHA-256 核对，从新版重新转换；不在旧 Harbor 包上手改。
4. **规则对所有答卷一样。** 豁免、扣分、容差写进细则，对每份答卷都生效；不给 Gold 单开免扣分支。某条"其实不算错"，只能改细则。
5. **答案不进作答环境。** Gold、rubric、评卷参考只放 `tests/` 或 `solution/`；`environment/` 下的东西会打进镜像，Agent 看得到。
6. **花钱、上线的动作先问。** `evalplat try`（真实判分模型回测）、`evalplat upload`（构建 + 参考解验收）、建 Job 都会产生费用。专家确认前不在平台建任务、不建 Job（"先不跑，我让专家确定了再跑"）。
7. **不提交密钥，不修改作答轨迹。** 题包里不放任何 key；跑出来的轨迹和判分原文是交付记录，不能改。

---

## 流程

### 0. 先确认交付形态

问清楚对方要的是什么：**Harbor 题包**，还是**对方自己的采集表**（例如 Excel 采集表 + input_files + solution）。
曾经出现过：我们做完整套 Harbor 包，对方要的其实是专家填的采集表——这时只需整理专家原始数据，不需要环境和判分程序，也不要把我们自己的 rubric 塞进去。

### 1. 收原始包

- 按 `00_原始包文件索引*.csv`（带 SHA-256）逐个核对，缺文件或哈希不符先停下问。
- 读 `00_修订说明`、交接说明、专家确认意见，列出本版和上一版的差异。
- 分清三类材料：**给 Agent 的**（题面、输入材料、空表/模板）、**给判分的**（评分细则、Gold、评卷参考、复核记录、错例）、**只存档的**（原始审核材料全量）。

### 2. 搭目录

从 `templates/rubric-judge/` 复制一份，改名为题号。目录含义：

```
<题号>/
├── task.toml                         # 元数据、时限、资源、网络、判分模型
├── instruction.md                    # 给 Agent 的题面（专家原文 + 环境说明）
├── environment/
│   ├── Dockerfile                    # 作答镜像（判分复用它）
│   └── input_files/input/...         # 输入材料 → 镜像里 /app/input/（只读）
├── solution/
│   ├── solve.sh                      # 参考解：把 Gold 原样拷到 /app/output/
│   └── golden_output/...             # Gold 原件（逐字节拷贝）
└── tests/
    ├── test.sh                       # 判分入口，写 /logs/verifier/reward.json
    ├── grader/                       # 通用判分程序（一般不用改）
    └── rubric/
        ├── rubric.md                 # 专家评分细则原文
        ├── items.json                # 评分项登记：ID、分值、组、前提、分批
        ├── instruction.md            # 题面副本（判分容器里看不到 /app 下的题面）
        ├── 判分说明.md               # 细则 → 程序的逐条对应、已知局限
        ├── reference/                # 只给判分模型看的 Gold/评卷参考
        └── source/                   # 原始审核材料存档（判分不读，可选）
```

纯数值、可程序比对的题用 `templates/deterministic/`。

### 3. 写 instruction.md

- 专家题面原文放前面，不改业务表述。
- 末尾加一段环境说明，固定写法：

  ```
  ---

  题包材料在 `/app/input/`（只读），空表为 `input/xxx.xlsx`。
  全部交付文件放在 `/app/output/`（当前工作目录为 `/app`）。
  ```
- 题面里的相对路径（`input/`、`材料/`）在 `/app` 下要真实存在。
- 写清：交什么、放哪、格式要求（或"不限文件格式"）、是否可以联网、结论必须给出（可以附限定条件）。
- 不要把评分目标、Gold 位置、豁免条目写进题面。
- 不要出现 `/tests`、`/solution`。

### 4. 写 Dockerfile

- 基础镜像用 `python:3.12-slim`（执行机已预置、pip/apt 走内网源）；其他外部镜像要先同步到 ACR。
- 判分依赖（openpyxl、pdfplumber、LibreOffice、中文字体等）一起装进镜像——判分复用作答镜像，判分时不能联网装依赖。
- 输入材料 `COPY input_files/ /app/`，`/app` 设为只读；`/app/output` 归 `agent` 用户可写。模板里已写好。

### 5. 写 task.toml

照模板改。必须注意：
- `[task] name` 用 `org/name` 格式（字母数字和 `._-`）；改版时 `version` 递增。
- 顶层 `artifacts = ["/app/output"]`：判分在独立容器里，不声明就拿不到作答文件。
- `[verifier] environment_mode = "separate"`：显式写，否则交付标准 S7 可能不过。
- 模型判分题在 `[metadata]` 写 `judge_model`（如 `gpt-6.1-sol`）；平台据此在判分阶段注入判分令牌。
- `network_mode`：题面允许查公开信息就 `public`，否则 `no-network`。
- 时限和资源按题目实际需要估；云沙箱最大 4 核 16G、单次最长 24 小时、磁盘 15G 且含镜像。

字段全集、默认值、拒收规则见 `references/format.md`。

### 6. 写判分

**模型判分（默认）**：
- `rubric.md` = 专家细则原文。
- `items.json` 登记细则里的每个评分项：`id`、`max`、`group`、`title`，以及细则写明的 `requires`（必要前提）、组折算 `scale`、`all_or_nothing`（只给满分或零分）、`no_deduct`（不设清单外扣分）、`deduct_group`/`deduct_note`（扣分规则）、`gold_target`（Gold 原件里的评分目标行）。合计必须等于 `full`（通常 100）。
- `reference/` 放 Gold 原件和评卷参考，只给判分模型。
- 有可以程序核对的数字落点（如报告期更新题的逐行数值），写 `tests/rubric/extra.py` 做确定性评分，其余交判分模型。
- 判分模型不可用时**不写 reward**（平台记判分出错，不记 0 分）；空卷直接 0 分，不调模型。通用判分程序已实现这两点。

写法细节、字段说明、经验见 `references/rubric.md`。

**确定性判分**：`test.sh` 在每条路径都写 `/logs/verifier/reward.txt` 或 `reward.json`，分数归一化到 0~1。

### 7. 放参考解（Gold）

- Gold 用专家定稿**原件**，逐字节拷贝，不删行、不重存、不另做"精简版"，记下 SHA-256。
- `solve.sh` 把原件拷到 `/app/output/`，再用 `sha256sum -c` 核对。
- Gold 内部不能自相矛盾；资料推不出来的数据写"作答资料未披露（待核）"，资料里有的不能误删；图片、扫描件、签章页不能丢。
- 用 Gold 对着细则逐条自检：正向项应全过，扣分项一条都不触发。

### 8. 本地预检

```bash
python3 scripts/check_package.py ./<题号>      # 结构、编码、字段、items 合计、答案泄漏
evalplat check ./<题号>                         # 服务端解析，不构建、不花钱
```

### 9. 回测（先问，会花钱）

用 `evalplat try` 跑，不建任务，3 天后自动删除：

```bash
evalplat try ./<题号> --wait                    # 参考解：模型判分题要求 ≥90（专家口径）
evalplat try ./<题号> --solution nop --wait     # 空卷：应为 0 或很低
```

再做变体包（只换 `solution/` 和题名）：等价另名、只写待核、分项错合计凑对、照抄输入、捏造事实、漏一项等，确认每个变体的得分符合细则预期。同一份 Gold 至少跑 3 轮看波动。方法和标准见 `references/backtest.md`。

### 10. 交专家确认，再上传

- 写《判分说明》（细则 → 程序逐条对应、已知局限）、《回测明细》（每个变体每轮得分）、《00_说明_请专家确认》（版本、改了哪些文件、哈希、待专家定的问题）。
- 每题打一个 zip，按题号命名，放网盘；旧版先移进回收站再上传同名文件。
- 专家确认后再 `evalplat upload ./<题号> --wait`；之后 `evalplat version baseline <版本ID> --nop 1 --oracle 2 --yes` 补齐 S4 基线（参考解连验收那次共 3 次）。

---

## 和用户/专家沟通

- 一律简体中文；结论先行，列表代替长段落。
- 发现细则和 Gold 冲突、细则有歧义、某条按字面所有模型都会错：列出来请专家定，不要自己挑一种改。
- 低分分析只讲模型为什么错、题目哪里需要澄清；不编造理由。
