# Rubric 设计说明（DEMO-0002）

## 1. 评分维度与权重

R01–R06 各对应一家公司（A～F）的 2025 年末资产负债率，维度均为“内容质量-数值与计算准确性”，
`method = "code"`（`json_value`，容差 0.0001），binary，等权各 1 分。确定性判据 100%，不调用判分模型。

## 2. 判分链路与 reward

`tests/test.sh` → `tests/grader/rubric_verify.py`：读取 `/app/output/answer.json`，逐家公司取值比对；
reward = 通过条数 ÷ 6。读不到文件或取不到值的项记未通过，原因写进 `reward_detail.json`。

## 3. 标准答案

标准值由 `environment/input_files/input/balance.csv` 计算（负债合计 ÷ 资产总计，保留 4 位），写在 `rubric.json` 各条 `check.value`；
参考解 `solution/solve.sh` 用同一公式生成。

## 4. 创作、审核与迭代

| 版本 | 日期 | 作者 / 评审人 | 改动 |
|---|---|---|---|
| 1.0.0 | YYYY-MM-DD | 作者：…；二审：… | 初稿 |
