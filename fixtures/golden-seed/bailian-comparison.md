# 百炼托管侧 vs 研判工坊：金场景对照说明

> **性质**：作品集向的**概念对照**（portfolio note），**不是**产品运行时、也不是把百炼接到本仓库的集成指南。  
> **读者**：面试官 / 评审者——用来讲清「框架 vs 运行时 vs 托管平台」分层，以及本仓库刻意落在哪一层。

---

## 1. 同一金问题（两侧共用）

个人/小团队应自建 Agent 编排（LangGraph 类），还是先上托管 Agent 平台（如百炼）？

英文种子表述（与本目录种子包一致）：

> Should an individual/small team self-build agent orchestration (LangGraph-class) or ship first on a managed agent (e.g. 百炼)?

两侧都回答**同一道题**；差别在「证据怎么进、编排谁管、闸门与 Trace 落在何处」，而不是换一道题。

---

## 2. 调研中的三层词汇（先对齐语言）

官方材料里可粗分为三层（命名来自 LangChain 自家对照页，也与多家厂商表述相容）。下表用中文把词钉死，避免面试时把「用了某 SDK」说成「有了运行时」或「上了托管平台」。

| 层级（英文） | 中文含义 | 典型职责 | 本对照中的落点 |
| --- | --- | --- | --- |
| **Agent framework** | Agent **框架** | 模型、工具、agent loop 等高层抽象 | 研判工坊：可替换 chat Provider；**不**绑定 OpenAI Assistants / Microsoft AutoGen |
| **Orchestration / runtime** | **编排 / 运行时** | 图/事件工作流、检查点、人机回环、长时状态 | 研判工坊：**LangGraph**（Planner → Researcher → Critic → Writer）+ 自有 HITL / Trace |
| **Managed platform** | **托管平台** | 控制台创建应用、托管观测与运维、应用 completion API | **百炼**智能体 / 工作流（经 DashScope `apps/{APP_ID}/completion` 一类调用） |

依据简述：

- LangGraph 官方定位偏 **orchestration / runtime**（长时、有状态、可 HITL），不是「托管控制台本身」。
- 百炼官方路径是「控制台创建智能体或工作流 → 应用 API completion」，落在 **managed platform**。
- 本仓库把百炼放在**对照叙事**里：帮助讲清分层，**不以百炼作为本应用的生产编排器**。

---

## 3. 概念跑法：同一金场景，两条路径

以下均为**概念推演**（作品集口述用），不要求本仓库调用百炼应用 API。

### 3.1 百炼托管侧（智能体 / 工作流）— 概念路径

1. 在百炼控制台创建**智能体**或**工作流**应用，把金问题写成系统/节点提示或工作流入口。
2. 把 landscape 调研与短摘录当作知识库 / 文件问答材料挂上（对应官方「知识库 / 文件」能力叙事）。
3. 经 DashScope 应用 API 发起 completion，得到一段「自建 vs 托管」倾向结论。
4. 观测与重试依赖**平台控制台**侧能力；人机闸门形态由平台产品能力决定，而非本仓库的两道硬闸契约。

**适合讲什么**：尽快上线对话/工作流、缩短运维与观测成本；适合「先托管、后加深」的产品节奏。

**不适合假装成什么**：不能把「控制台里跑通了一次 completion」说成「本仓库已用百炼做生产编排」。

### 3.2 研判工坊（本仓库）— 产品路径

1. 注册/登录 → 打开金路径项目（或跑 `scripts/seed_golden_project.py` 种子）。
2. 材料包已在应用内可检索；用**同一金问题**启 run（可选勾选产出清单）。
3. LangGraph 流水线：Planner 拆题 → Researcher 只读材料（联网默认关）→ Critic 打回无锚主张 → Writer 组装备忘录。
4. 两道硬闸：联网闸、清单闸；拒绝联网仍可完成；拒绝清单仍保留备忘录。
5. 备忘录主张带引用锚点；Run Trace 一等公民展示节点、HITL、Critic bounce、粗粒度耗时。

**适合讲什么**：自建 **runtime**——图编排、检查点、自有 HITL、可审计 Trace；面试时可指着 Trace 讲多 Agent 价值，而不依赖厂商控制台。

---

## 4. 对照表（面试一页纸）

| 维度 | 百炼托管侧（对照） | 研判工坊（本产品） |
| --- | --- | --- |
| 金问题 | 同一道「自建编排 vs 托管平台」 | 同一道 |
| 分层落点 | Managed platform | Orchestration / runtime（LangGraph） |
| 证据 | 知识库 / 文件等平台能力（概念） | 项目材料包 + 检索 + 锚点策略 |
| 编排谁管 | 平台应用（智能体 / 工作流） | 本仓库图：四业务 Agent + 硬闸 |
| 人机闸门 | 依平台产品能力 | 产品契约：联网闸 + 清单闸 |
| 可观测 | 平台控制台 | 一等 Run Trace API / UI |
| 与本应用关系 | **仅文档对照，不是生产编排器** | 生产编排与演示主路径 |

---

## 5. 刻意不做 / 刻意回避（与 spec 对齐）

1. **百炼不是本应用的生产编排器**  
   README 延后路线图与架构叙事已写明：不以百炼（或其它托管控制台）作为主生产编排器。本页存在，是为了作品集能**对照讲述**，不是为了把 completion 接到 FastAPI 主路径。

2. **不绑定 OpenAI Assistants API**  
   Assistants 已弃用路线（官方迁移指向 Responses 等）；本产品聊天经可替换 Provider，不把编排押在 Assistants 线程形态上。

3. **不使用 Microsoft AutoGen**  
   AutoGen 进入 maintenance mode，继任叙事指向 Microsoft Agent Framework；本仓库编排落在 LangGraph runtime，避免押在已维护模式的多 Agent 框架上。

4. **框架层保持可替换**  
   「不绑定 Assistants / AutoGen」不等于「没有 framework 层」：模型调用仍经 Provider 适配；真正钉死的是 **runtime = LangGraph + 自有闸门/Trace**。

---

## 6. 口述一句（金路径收束）

我们自建的是 **runtime 层**（LangGraph + 闸门 + Trace）；百炼代表 **managed platform 对照层**——帮助回答金问题，但**不是**本应用的生产编排器。

---

## 7. 相关入口

- 种子材料与评测清单：[`README.md`](README.md)
- Landscape 三层表：[`materials/agent-dev-landscape.md`](materials/agent-dev-landscape.md)
- LangGraph 短摘录：[`materials/excerpt-langgraph-runtime.md`](materials/excerpt-langgraph-runtime.md)
- 百炼短摘录：[`materials/excerpt-bailian-modes.md`](materials/excerpt-bailian-modes.md)
- 仓库总览与三分钟演示：[根 README](../../README.md)
