# 金路径种子包（golden seed）

本目录是**可进 git、可在应用内上传**的演示材料包，对应金问题：

> Should an individual/small team self-build agent orchestration (LangGraph-class) or ship first on a managed agent (e.g. 百炼)?

## 内容

| 路径 | 说明 |
| --- | --- |
| `materials/agent-dev-landscape.md` | Agent 开发生态调研笔记（一手来源分层：framework / runtime / managed） |
| `materials/excerpt-langgraph-runtime.md` | LangGraph 短官方摘录（编排/运行时） |
| `materials/excerpt-bailian-modes.md` | 百炼应用模式短官方摘录（托管侧） |
| `eval-checklist.md` | 3–5 条固定评测场景 |
| `bailian-comparison.md` | 作品集：百炼托管侧 vs 研判工坊概念对照（非运行时） |

## 如何写入应用

1. 启动 Postgres + API（见仓库根 README）。
2. 执行：

```bash
cd api
python ../scripts/seed_golden_project.py
```

脚本会注册/登录演示账号、创建金路径项目并上传 `materials/` 下全部文件。随后在 Web 工作台打开该项目，用默认金问题启 run。

也可在 UI 中手动「上传材料」，选择本目录 `materials/` 内文件。
