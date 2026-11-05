# 回测与交付

## 1. 先本地，后平台

| 步骤 | 命令 | 花钱 |
|---|---|---|
| 结构预检 | `python3 scripts/check_package.py ./题号` | 否 |
| 服务端解析 | `evalplat check ./题号` | 否 |
| 本地跑判分流程 | 用假判分（一律满分）或自己的 key 跑 `rubric_verify.py`，见下 | 自己的 key 会花钱 |
| 平台试跑 | `evalplat try ./题号 [--solution nop] --wait` | 是（构建 + 判分模型）|
| 上传验收 | `evalplat upload ./题号 --wait` | 是 |

平台上的动作先征得负责人同意。

### 本地跑判分

```bash
# 在题目镜像里或装好依赖的本机
mkdir -p /tmp/ws /tmp/logs && cp solution/golden_output/* /tmp/ws/
JUDGE_API_KEY=... JUDGE_BASE_URL=https://.../v1 JUDGE_MODEL=gpt-6.1-sol \
python3 tests/grader/rubric_verify.py --task tests/rubric \
  --instruction tests/rubric/instruction.md --workspace /tmp/ws --logs /tmp/logs
cat /tmp/logs/reward_detail.json
```

先确认：空目录得 0 且不调模型；前提连锁生效（前提项失分时依赖项为 0）；items 合计正确。

## 2. 变体包

克隆正式包，**只换 `solution/` 和 `[task] name`**，其余完全一样，用 `evalplat try` 跑：

| 变体 | 预期 |
|---|---|
| Gold 原件 | ≥90（专家口径；平台验收只要求 >0）|
| 空卷（`--solution nop`）| 0 或很低 |
| 等价另名/等价表述 | 与 Gold 同分 |
| 只写"待核"/不下结论 | 只保留对象和字段分 |
| 分项错、合计凑对 | 分项和合计都失分 |
| 照抄输入原稿 | 很低 |
| 漏一项 | 只失该项 |
| 捏造事实（日期/主体/金额）| 按细则扣分 |
| 多报一个假对象 | 按细则扣分 |

每个变体写清"按细则应得多少"，和实际得分对比。不一致时：先看 `reward_detail.json` 的证据和理由，分清是**判分程序问题**（抽字、摘取、认文件）还是**细则问题**（歧义、冲突），细则问题交专家定。

## 3. 多轮与波动

- Gold 至少跑 3 轮，记录每轮总分和逐项分。
- 同内容应同分；波动 >2 分要找原因。
- 改了判分程序或细则后，**全部变体重跑**（曾出现：更新判分脚本后 Gold 从 0.979 掉到 0.52，交付包里写的还是旧分）。
- 包超过试跑 512MB 时，回测副本可以删掉判分不读的大材料，正式包保持完整。

## 4. 交付材料

每题一个 zip（按题号命名），外加：

- `00_说明_请专家确认.md`：版本号、本版改了哪些文件、Gold 和关键文件的 SHA-256、待专家定的问题。
- `判分说明.md`（在包里 `tests/rubric/`）：细则 → 程序对照表、Gold 来源和哈希、已知局限。
- `回测明细_<日期>.md`：每个变体每轮的总分和逐项分、与预期的差异。

放网盘时：网盘没有改名接口，同名上传会 409，旧版先移进回收站再上传；上传后核对大小。

## 5. 上传后

```bash
evalplat upload ./题号 --wait
evalplat version baseline <版本ID> --nop 1 --oracle 2 --yes   # S4：空跑 1 次，参考解共 3 次
evalplat version baselines <版本ID>
```

建 Job、选模型、并发、次数由负责人决定（例如 GPT 批次默认同时 4 个、每题 3 次）。

## 6. 对方验收常见要求（以当次合同为准）

- 每个模型至少 3 次（推荐 5 次）。
- 参考答案重复判分 ≥3 次，得分 ≥0.9–0.95；空跑 0。
- 单题难度：SOTA 得分不能全 0，也不能太高（某次要求 ≤40）；数据集整体难度 0.1–0.5。
- 输入文件随包交付，不依赖外链。
- 报告：来源与分布、Rubric 设计、难度测试、判分准确性；收录理由、修订历史、工时、AI 辅助披露、防作弊测试。
- 近重复检测：材料高度相似的题（如两题共用 17 个文件）要单独说明区别。
- 每个 Trial 交判分原文 `judge/calls.jsonl`（平台自动保存）。
- 轨迹文件不得修改。
