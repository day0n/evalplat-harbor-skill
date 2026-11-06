# Rubric 设计说明（DEMO-0001）

> 每题一份，随题包交付（阿里标准“报告二：Rubric 设计说明”）。下面是写法示例，按本题实际填写。

## 1. 评分维度与权重

| ID | 维度（tag） | 判定方式 | 类型 | 权重 | 设计依据 |
|---|---|---|---|---|---|
| R01 | 内容质量-数值与计算准确性 | code：number | binary | 20 | 题面要求核查 2025 年末资产负债率；核心数值，权重最高之一 |
| R02 | 内容质量-事实忠实性 | llm | binary | 15 | 题面“说明依据”；取数须可追溯到《财务摘要》 |
| R03 | 内容质量-结论正确性 | llm | binary | 25 | 题面要求明确结论；依赖 R01（requires） |
| R04 | 内容质量-数值与计算准确性 | code：number | binary | 10 | 题面要求与 2024 年末对比 |
| R05 | 内容质量-分析与论证质量 | llm | gradient（1 / 0.5 / 0） | 20 | 题面要求分析变动原因 |
| R06 | 指令遵循 | code：file_exists | binary，hurdle | 10 | 交付物必须在 output/；没有交付时整题 0 分 |
| N01 | 内容质量-事实忠实性（负向） | llm | binary，最多 3 次 | 每次 −5 | 题面“不要自行编造” |

条数与占比（`python3 tests/grader/rubric_schema.py tests/rubric/rubric.json` 输出）：
正向 6 条、负向 1 条；确定性 3 条（加权 40%）、LLM 3 条（加权 60%）；客观项 100%；显式要求 100%。

## 2. 判分链路

1. `tests/test.sh` → `tests/grader/rubric_verify.py`，读取并校验 `rubric.json`。
2. 读取真实产物：遍历 `/app/output/` 全部文件；docx 接受全部修订后读正文与表格，pdf 按页抽取，xlsx 读单元格实际值
   （公式没有缓存值时先用 LibreOffice 重算），全部文本送判，不摘取、不截断；同一文件多种格式只送一份（docx 优先）。
   全文超过 15 万字时按行完整切段、逐段通读摘录后再判定；解析失败、抽不出文字的页写进 `reward_detail.json` 的
   `coverage`，不当空答案；能抽出的内容没送到判分模型时不写 reward。
3. `method = "code"` 的项由程序检查：数值项要求指标、期间与数值出现在同一行并带单位，不做全文搜数字。
4. `method = "llm"` 的正向项分批交给判分模型，模型只输出 yes/no 或档位键、答卷原文证据与理由；
   负向项在正向项评完后单独判定，已在正向项失分的同一错误不再扣。
5. 程序聚合，模型不算总分。

## 3. reward 计算公式

```
正向得分 = Σ weight × 档位值（binary 为 0/1；requires 未满足记 0）
扣分     = Σ weight × 命中次数（负向 binary）或 weight × 档位值（负向 gradient）
总分     = max(0, Σ_组 max(0, 组内正向 − 组内扣分) × scale − 总分扣分)；hurdle 未满足时总分为 0
reward   = 总分 ÷ Σ_组（组内正向 weight 之和 × scale），四舍五入按 scoring.round
```

本题无分组，满分 100：Gold 预期 1.0；空卷 0（R06 hurdle）。

## 4. Gold 与评卷参考

- `solution/golden_output/核查结论.md`，与 `tests/rubric/reference/` 中副本逐字节一致；SHA-256 见 `solution/solve.sh`。

## 5. 创作、审核与迭代

| 版本 | 日期 | 作者 / 评审人（专业背景） | 工时 | 改动 |
|---|---|---|---|---|
| 1.0.0 | YYYY-MM-DD | 作者：…；二审：… | 初稿 x h / 审核 y h | 初稿 |

- AI 辅助：如有，写明模型名、Prompt、生成范围，以及人工评审修订的内容（修订 diff）。
- 判分模型：平台判分用 `task.toml` 的 `judge_model`；跨 Judge 一致性测试的模型与结果见批次报告。
