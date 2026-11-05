# 造题检查清单

## 交给专家确认前

**原始包**
- [ ] 已确认交付形态（Harbor 包 / 对方采集表）
- [ ] 按索引 SHA-256 核对原始包齐全，用的是最新版
- [ ] 有新版时从新版重转，没在旧包上手改

**题面 instruction.md**
- [ ] 专家原文未改动，末尾有环境说明（输入在 `/app/input/`，交付放 `/app/output/`）
- [ ] 题面引用的路径都真实存在
- [ ] 写清交什么、格式（或"不限文件格式"）、能否联网、必须给结论
- [ ] 没有评分目标、Gold 位置、豁免条目、`/tests`、`/solution`
- [ ] `tests/rubric/instruction.md` 与题面一致

**环境**
- [ ] Dockerfile 基于 `python:3.12-slim`（或已同步 ACR 的镜像）
- [ ] 判分依赖、OCR、中文字体已装进镜像
- [ ] `/app` 只读、`/app/output` 归 agent 可写
- [ ] `environment/` 下没有 Gold、rubric、评卷参考
- [ ] 镜像 + 输入材料 < 15G（云沙箱）

**task.toml**
- [ ] `name` 合法、`version` 已递增
- [ ] `artifacts = ["/app/output"]`
- [ ] `[verifier] environment_mode = "separate"`
- [ ] 模型判分题写了 `judge_model`；`GRADE_JUDGE_BUDGET` < `verifier.timeout_sec`
- [ ] `network_mode` 与题面一致
- [ ] CPU/内存在 4c16g 以内，时限 ≤24 小时

**细则与判分**
- [ ] `rubric.md` 是专家原文，所有副本一致
- [ ] `items.json` 每项都能在细则里找到，合计 = `full`
- [ ] `requires`、`all_or_nothing`、`no_deduct`、扣分组都有细则依据
- [ ] 没有只对 Gold 生效的分支
- [ ] `判分说明.md` 有"细则 → 程序"对照表和已知局限

**Gold / 参考解**
- [ ] Gold 是完整原件、逐字节拷贝，SHA-256 已记录
- [ ] `solve.sh` 拷贝后 `sha256sum -c` 校验
- [ ] Gold 无内部矛盾；图片、扫描件、签章页齐全
- [ ] 用 Gold 对细则逐条自检：正向全过、扣分零触发

**回测**
- [ ] `check_package.py` 无错误；`evalplat check` 通过
- [ ] （已获同意）Gold ≥90 且至少 3 轮，波动已记录
- [ ] 空卷 0 或很低
- [ ] 等价答卷同分；各错例得分符合细则预期
- [ ] 改过判分程序或细则后全部重跑

**交付材料**
- [ ] 每题一个 zip，按题号命名
- [ ] `00_说明_请专家确认.md`、`回测明细`、待定问题清单

## 专家确认后、上传时

- [ ] 得到明确确认（"可以上了"）再 `evalplat upload`
- [ ] 验收通过；`version baseline` 补齐 S4
- [ ] 建 Job 的模型、次数、并发由负责人定
