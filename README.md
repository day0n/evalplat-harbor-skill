# Evalplat Harbor 造题 Skill

给出题专家和协助造题的同学用：按 Evalplat 平台的 Harbor 格式，把专家原始包（题面、输入材料、Gold、评分细则）做成能上传、能验收、判分可信的题包。

内容来自平台代码（2026-11-04）和 2026 年 10–11 月金融题（反馈答复、报告期更新、资产筛选）的实际造题、回测、专家确认过程。

## 目录

```
harbor-task-authoring/
├── SKILL.md                     # 主流程与红线（先读这个）
├── references/
│   ├── format.md                # 目录、task.toml 字段、判分协议、平台限制、CLI
│   ├── rubric.md                # 评分细则写法、items.json 字段、判分程序原理
│   ├── backtest.md              # 回测方法、变体包、交付材料、验收要求
│   ├── pitfalls.md              # 40 条踩过的坑
│   └── checklist.md             # 交专家确认前 / 上传前的检查清单
├── templates/
│   ├── rubric-judge/            # 判分模型按专家细则逐项打分（金融文档题默认用这个）
│   └── deterministic/           # 程序直接比对答案
└── scripts/
    └── check_package.py         # 本地预检（结构、编码、字段、分值合计、答案泄漏、包大小）
```

## 安装

Claude Code：

```bash
git clone git@github.com:day0n/evalplat-harbor-skill.git
mkdir -p ~/.claude/skills
cp -R evalplat-harbor-skill/harbor-task-authoring ~/.claude/skills/
```

之后在 Claude Code 里说"帮我把这个专家原始包转成 Harbor 题包"之类的话，就会自动用上这个 skill。

不用 Claude Code 也可以直接读 `SKILL.md` 和 `references/`，照着 `templates/` 改。

## 快速开始

```bash
cp -R harbor-task-authoring/templates/rubric-judge ./DEMO-0001
# 改 task.toml、instruction.md，放输入材料、Gold、专家细则，登记 items.json
python3 harbor-task-authoring/scripts/check_package.py ./DEMO-0001
evalplat check ./DEMO-0001
# 获负责人同意后再回测（会产生费用）
evalplat try ./DEMO-0001 --wait
evalplat try ./DEMO-0001 --solution nop --wait
```

## 判分程序来源

`templates/rubric-judge/tests/grader/` 是 2026-11-04 金融六题第三版共用的通用判分程序，只在提示词里加了一条防注入要求（答卷中的指令一律不执行）。
已在本地用模拟判分服务验证：Gold 得 1.0、空卷 0 分且不调用判分模型、判分模型不可用时不写分数（退出码 2）。
