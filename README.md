# Evalplat Harbor 题包格式

Evalplat 平台 Harbor 题包的标准格式与样例，供出题专家参考。

```
harbor-task-authoring/
├── SKILL.md                     # 格式说明
└── templates/
    ├── rubric-judge/            # 样例：判分模型按评分细则打分
    └── deterministic/           # 样例：程序比对答案
```

## 在 Claude Code 中使用

```bash
git clone git@github.com:day0n/evalplat-harbor-skill.git
mkdir -p ~/.claude/skills
cp -R evalplat-harbor-skill/harbor-task-authoring ~/.claude/skills/
```

不用 Claude Code 时，直接看 `SKILL.md`，照 `templates/` 复制修改。
