# 研判工坊（judgment-forge）

多人隔离的**研判工作台**：上传材料包 → LangGraph 多 Agent 流水线 → 人机闸门 → 带引用锚点的决策备忘录（可选行动清单）→ 一等公民 Run Trace。

**金问题（演示默认题）**：个人/小团队应自建 Agent 编排（LangGraph 类），还是先上托管 Agent 平台（如百炼）？

## 写给面试官的架构叙事

本产品刻意落在官方常见的三层对照上（详见种子包调研笔记）：

| 层级 | 含义 | 本仓库落点 |
| --- | --- | --- |
| **Agent framework** | 模型 / 工具 / agent loop 抽象 | 不绑定 Assistants / AutoGen；聊天经可替换 Provider |
| **Orchestration / runtime** | 图编排、检查点、人机回环 | **LangGraph**（Planner → Researcher → Critic → Writer） |
| **Managed platform** | 托管控制台 / 应用 completion | **不作为本应用运行时**；作品集对照见 [`fixtures/golden-seed/bailian-comparison.md`](fixtures/golden-seed/bailian-comparison.md)（仅文档叙事） |

四个业务 Agent（图本身不算业务 Agent）：

1. **Planner** — 拆子问题与证据需求  
2. **Researcher** — 默认只读材料包；联网工具须经 HITL  
3. **Critic** — 打回缺锚点主张与过度推断（bounce 写入 Trace）  
4. **Writer** — 组装备忘录；可选清单草稿仍须第二道闸

两道硬闸（v1）：

1. **联网闸** — web/search 默认关；批准前不得外呼  
2. **清单闸** — 仅当启动时勾选「产出清单」且人工批准才定稿；拒绝仍保留备忘录

技术栈：`Next.js`（桌面向工作台）+ `FastAPI`（鉴权 / 项目 / 材料 / runs / HITL / Trace）+ `PostgreSQL`。

## Local stack

### 1. Postgres

```bash
docker compose up -d
```

Default connection (also in `api/.env.example`):

```
postgresql://judgment:judgment@localhost:5432/judgment_forge
```

### 2. API

```bash
cd api
python -m pip install -e ".[dev]"
copy .env.example .env   # Windows; or cp on Unix
uvicorn judgment_forge.app:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

### 3. Web shell

```bash
cd web
npm install
copy .env.example .env.local   # Windows; or cp on Unix
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

API 已对 `localhost:3000` 开启 CORS。

### 4. 金路径种子（可选）

```bash
cd api
python ../scripts/seed_golden_project.py
```

会创建演示账号（默认 `golden-demo@example.com` / `golden-demo-pass`）、金路径项目，并上传 `fixtures/golden-seed/materials/`（landscape 调研 + LangGraph / 百炼短摘录）。材料说明见 [`fixtures/golden-seed/README.md`](fixtures/golden-seed/README.md)。

## 三分钟演示脚本

前置：Postgres + API + Web 已启动；建议先跑上一节种子脚本。

| 时间 | 动作 | 口述要点 |
| --- | --- | --- |
| 0:00–0:20 | 打开工作台，登录种子账号（或现场注册） | 多用户隔离：项目/材料/run 均按所有者鉴权 |
| 0:20–0:50 | 打开「金路径：自建编排 vs 托管 Agent」项目，确认材料 `ready` | 证据包在应用内可检索；主张须可锚回材料 |
| 0:50–1:20 | 用默认金问题启 run，**勾选**产出清单 | 说明四 Agent 流水线；web 默认关闭 |
| 1:20–2:00 | 若出现联网闸 → **拒绝**；继续等到清单闸 → **批准或拒绝**其一 | 强调两道 HITL：拒网仍可完成；拒清单仍保留备忘录 |
| 2:00–2:40 | 打开备忘录：结论 / 选项对照 / 风险 / 下一步；点开引用锚点 | 材料事实带锚；无锚标推断/未知 |
| 2:40–3:00 | 打开 Run Trace：节点、HITL、Critic bounce、粗粒度耗时 | 一等 Trace，不依赖厂商控制台讲清多 Agent 价值 |

金路径口述句：**我们自建的是 runtime 层（LangGraph + 闸门 + Trace），托管平台是对照层，不是本应用的生产编排器。**

## 评测清单（摘要）

完整条目见 [`fixtures/golden-seed/eval-checklist.md`](fixtures/golden-seed/eval-checklist.md)：

1. 金路径跑通并产出结构化备忘录  
2. 材料主张带 **anchors**；无锚不得装事实  
3. Trace 可见 **Critic bounce**  
4. **无意外联网**（拒绝联网闸后无 web 工具调用）  
5. （可选）清单闸拒绝仍有备忘录；进行中可取消

## v1 延后路线图（明确不做）

以下能力写在 README 以示范围纪律，**不在当前验收范围**：

- Computer Use / 桌面或浏览器操控 Agent  
- 语音 / Realtime Agent  
- 任意代码执行沙箱（Code Agent sandbox）  
- 无人值守定时研判  
- 团队空间、邀请、RBAC、SSO、分享链接  
- 默认写入 GitHub/Jira 等外部系统  
- 以百炼（或其它托管控制台）作为本应用的主生产编排器

## 作品集：百炼对照说明

同一金问题在「百炼托管智能体/工作流」与「研判工坊」上的概念对照（框架 / 运行时 / 平台），见 [`fixtures/golden-seed/bailian-comparison.md`](fixtures/golden-seed/bailian-comparison.md)。**百炼不是本应用生产编排器**；该页仅供面试/作品集叙事。

## Tests

Primary seam: JudgmentForge HTTP API.

```bash
cd api
python -m pytest
```

Requires Postgres reachable at `DATABASE_URL`.
