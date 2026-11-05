# Harbor 题包格式与平台限制

依据：平台代码 `packages/task_types/src/evalplat_task_types/harbor/spec.py`、Harbor 0.23 `models/task/config.py`、
`apps/api/src/evalplat_api/templates.py`、`packages/core/.../delivery_standard.py`（2026-11-04 版本）。

## 1. 目录

| 路径 | 必需 | 说明 |
|---|---|---|
| `task.toml` | 是 | 缺了报「缺少 task.toml」 |
| `instruction.md` | 是 | Agent 看到的题面，UTF-8 |
| `environment/Dockerfile` | 是 | 作答镜像；或在 `[environment]` 写 `docker_image` 代替 |
| `tests/test.sh` | 是 | 判分入口；`tests/` 整个目录在判分时上传到 `/tests` |
| `solution/solve.sh` | 建议 | 参考解，在 `/solution` 下执行；没有就跳过验收，但交付标准 S4 缺参考解基线 |
| `steps/<名>/` | 否 | 多步骤题；ECS 执行机和云沙箱都不支持，不要用 |

- Agent 作答时**看不到** `tests/` 和 `solution/`。
- 判分输出：`/logs/verifier/`；`test.sh` 的标准输出存在 `/logs/verifier/test-stdout.txt`。
- 平台最小模板：`evalplat task-template --kind harbor -o ./demo`。

## 2. task.toml

### 金融文档题的推荐写法

```toml
schema_version = "1.4"
artifacts = ["/app/output"]          # 也可写 [{source = "/app/output"}]

[task]
name = "docrev/fin-xxx-0001"         # org/name，字母数字和 ._-，字母或数字开头
version = "1.0.0"                    # 改版递增
description = "题号_标题（题型）"

[metadata]
judge_model = "gpt-6.1-sol"          # 模型判分题必写；确定性判分题删掉
task_family = "资产筛选"              # 自定义元数据，平台原样保存
source_package = "<网盘原始包 ID>"

[[metadata.deliverables]]            # 自定义：交付物说明，便于审核
path = "/app/output/"
required = true
desc = "最终核定结果（一笔一行，可用随题空表）"

[agent]
timeout_sec = 14400.0                # Agent 作答时限

[verifier]
timeout_sec = 7200.0                 # 判分时限（模型判分要留足）
user = "root"
environment_mode = "separate"        # 显式写，交付标准 S7 需要

[verifier.env]                       # 判分程序读的参数
GRADE_REASONING_EFFORT = "max"       # 判分模型思考强度（Responses 协议）
GRADE_JUDGE_PARALLEL = "4"           # 并发批数
GRADE_CALL_TIMEOUT = "1200"          # 单次调用超时（秒）
GRADE_JUDGE_BUDGET = "6600"          # 全部调用总预算（秒），要小于 verifier.timeout_sec
GRADE_MAX_OUTPUT_TOKENS = "32000"    # max 思考时推理也算输出，太小会返回空

[environment]
os = "linux"
build_timeout_sec = 3600.0
network_mode = "no-network"          # 题面允许查公开信息时用 "public"
cpus = 4
memory_mb = 16384
storage_mb = 10240
```

### 字段说明

| 表 | 字段 | 默认 | 规则 |
|---|---|---|---|
| 顶层 | `artifacts` | 空 | 作答结束后采集、回灌到独立判分容器的原路径。路径不能含 `..`。**不写判分就看不到作答文件** |
| `[task]` | `name` | — | 必填，`org/name` |
| `[metadata]` | `judge_model` | — | 必须在平台允许列表里（代码默认：`gemini-3.5-flash`、`gemini-3.8-flash`、`gpt-6.1-sol`）|
| | `category` | — | 一级类别只有 `coding`、`多模态`、`cyber`、`未分类`；写其他值会转成三级分类 |
| | `subcategory` | — | ≤100 字，不能含 `/` |
| | `execution` | — | 写了就拒收 |
| `[agent]` | `timeout_sec` | 36 小时 | 上限 36 小时；云沙箱单次最长 24 小时 |
| `[verifier]` | `timeout_sec` | 600 | 模型判分题按调用次数估，一般 3600–7200 |
| | `environment_mode` | `separate` | 显式写 `"separate"` |
| | `env` | — | 判分时的环境变量 |
| `[environment]` | `cpus` | 1 | 云沙箱：内存/CPU 比 1~4，生产模板只有 2c4g、4c8g、4c16g |
| | `memory_mb` | 2048 | |
| | `storage_mb` | 10240 | 平台不校验；云沙箱整盘 15G 且包含镜像 |
| | `build_timeout_sec` | 600 | 平台构建至少给 4 小时 |
| | `network_mode` | `public` | `public` / `no-network` / `allowlist`（配 `allowed_hosts`，只能写精确域名、IPv4、CIDR）|
| | `gpus` | 0 | 不支持 |
| | `env` | — | 不能写 `${VAR}`；平台不向任务传凭证 |

拒收（HTTP 422）：`os = "windows"`、`tpu`、`gpu_types`、`env` 里的 `${VAR}`、`judge_model` 不在允许列表、任务名不合法、`metadata.execution`。

## 3. 判分协议

### 分数文件

- `test.sh` 每条路径都要写分：`/logs/verifier/reward.txt`（一个数）或 `/logs/verifier/reward.json`（对象，值都是数；有 `reward` 键就用它，否则取平均）。两个都有以 json 为准。
- 没写、为空、不是数、NaN/Inf → **判分出错**（不是 0 分）。
- 平台不截断分数，脚本自己归一化到 0~1。
- 可选：`/logs/verifier/checks.json` 展示逐条得分；通用判分程序另写 `reward_detail.json`（逐项分数、证据、理由、日志）。
- 开头先删掉旧的分数文件，不信任 Agent 留下的任何东西。

### 模型判分

- `[metadata] judge_model` 声明后，平台**只在判分阶段**注入：`GEMINI_API_KEY`（判分令牌）、`GOOGLE_GEMINI_BASE_URL`（网关地址 + `/gemini`）、`MODEL_NAME`。Agent 和参考解拿不到。
- 网关按路径区分协议：`gpt-*` → `<网关>/openai/v1/responses`；`claude-*` → `<网关>/anthropic/v1/messages`；其他 → Gemini 原生。令牌只放行绑定的那个模型。模板里的 `tests/grader/judge.py` 已处理。
- 断网题里网关地址也会放行。
- 判分模型偶尔超时或不返回合法 JSON，判分程序要自己重试；预算内仍拿不到结果就**不写 reward**、非零退出。
- 每个 Trial 的判分原文（完整请求和响应）平台自动存为 `judge/calls.jsonl`，随交付包导出。

### 独立判分容器

- 判分在新容器里跑，复用作答镜像，不继承作答时的文件系统；作答文件靠 `artifacts` 回灌。
- 判分依赖必须在 Dockerfile 里装好；判分时不要联网装包。

## 4. 验收与交付标准

- **上传后**：构建镜像 → 跑参考解 → 判分。普通题要得 1.0；模型判分题得分 > 0 即可用。
- `evalplat version revalidate <版本ID>` 重新验收；`version rebuild` 重试失败的构建。
- **包大小**：试跑/普通上传 ≤512MB；大题包 ZIP ≤10GB（只有被 Dockerfile 打进镜像的 `environment/` 数据文件可以很大），其余解压后 ≤512MB，文件数 ≤20000。

交付标准（导出时检查，告警不阻断导出）：

| 编号 | 内容 |
|---|---|
| S1 | 题面里没有 canary（Harbor 只剥离开头整行注释）|
| S2 | `environment/` 下拷进容器的文件没有 canary |
| S3 | 作答轨迹里没有 canary |
| S4 | 有基线：参考解全部 1.0（模型判分题 > 0）、空跑全部 0，各至少一次 |
| S5 | 判分用的 tests/ 与交付题包一致 |
| S6 | Agent 没访问本题上游 |
| S7 | 分数来自独立判分（`environment_mode = "separate"`）|
| S8 | 外部导出净化后无残留 |

## 5. 运行环境

- 生产上构建、验收、`evalplat try` 跑在 **ECS 执行机**；`jobs create --backend fc-sandbox` 的 Job 在**阿里云云沙箱**作答。两边限制都要满足：
  - ECS 执行机：只支持单镜像，不能写 `[verifier.environment]`、不能有 `tests/Dockerfile`、不能多步骤；没有公网，只能访问阿里云内网源。
  - 云沙箱：最大 4c16g、单次 ≤24 小时、整盘 15G 含镜像；不支持 Compose、GPU、KVM；公网只能访问国内站点。
- 基础镜像用 `python:3.12-slim`；其他 Docker Hub 镜像先同步 ACR。

## 6. 常用命令

```bash
evalplat login                                     # 浏览器批准，保存个人令牌
evalplat guide                                     # 常用流程速查
evalplat task-template --kind harbor -o ./demo     # 最小模板

evalplat check ./题号                              # 只解析，不上传、不花钱
evalplat try ./题号 --wait                         # 参考解试跑（花钱：构建 + 判分模型）
evalplat try ./题号 --solution nop --wait          # 空跑
evalplat try ./题号 --keep-on-failure 2h --wait    # 未通过时保留现场，evalplat sandbox attach <ID> 进入
evalplat previews list | show <ID> --wait | trace <ID> | artifacts <ID> -o r.tar.gz

evalplat upload ./题号 --wait [--timeout 秒]        # 上传（构建 + 参考解验收，花钱）
evalplat version show <版本ID> --wait
evalplat version baseline <版本ID> --nop 1 --oracle 2 --yes   # 登记 S4 基线（--oracle 是验收之外再跑几次）
evalplat version baselines <版本ID>
evalplat task content <任务ID> --file tests/test.sh
```

- `--wait`：未通过退出码 1，超时退出码 5（不取消云端运行）。
- 不要把 `evalplat try` 的输出接 `| head`：SIGPIPE 会把命令杀掉。
- 上传目录时 CLI 跳过 `.git`、`__pycache__`、`.venv`、`node_modules`、`.DS_Store`。

## 7. 脚本与文件

- `solve.sh`、`test.sh` 第一行写 `#!/bin/bash`，LF 换行（CRLF 会破坏 shebang）。
- 路径一律绝对路径：`/app`、`/app/output`、`/tests`、`/solution`、`/logs/verifier`。
- 所有文本 UTF-8；中文文件名打 zip 时用 UTF-8。
