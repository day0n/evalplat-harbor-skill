# Evalplat Harbor 题包格式

Evalplat 平台 Harbor 题包的标准格式与样例，供出题专家参考。格式对齐阿里《Finance RL 数据采购标准 v20261030》：
评分标准统一写在 `tests/rubric/rubric.json`，判分模型只做逐项判定，总分由程序计算。

```
harbor-task-authoring/
├── SKILL.md                     # 格式说明
└── templates/
    ├── rubric-judge/            # 样例：判分模型 + 程序检查，按 rubric.json 判分
    └── deterministic/           # 样例：全部评分项由程序比对
```

## 在 Claude Code 中使用

```bash
git clone git@github.com:day0n/evalplat-harbor-skill.git
mkdir -p ~/.claude/skills
cp -R evalplat-harbor-skill/harbor-task-authoring ~/.claude/skills/
```

不用 Claude Code 时，直接看 `SKILL.md`，照 `templates/` 复制修改。写完 rubric.json 后运行校验：

```bash
python3 tests/grader/rubric_schema.py tests/rubric/rubric.json
```
