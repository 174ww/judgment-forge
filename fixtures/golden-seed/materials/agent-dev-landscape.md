# 当前 Agent 开发生态调研（一手来源）

> **调研日期**：2026-07-21  
> **问题**：当前的 agent 开发应用有哪些？（同时覆盖「构建 Agent 的工具/框架」与「官方文档中的应用类型/用例」）  
> **方法**：仅采信官方文档、GitHub 组织 README、厂商开发者门户与一手 API/规格页；二手榜单与自媒体综述不作为事实依据。

---

## 1. 研究问题与方法

### 1.1 研究问题

用户关心「当前 Agent 开发应用有哪些」。本报告将其拆为两层：

1. **开发侧**：开发者用来构建 Agent 的框架 / SDK / 托管平台是什么，官方如何定位。
2. **应用侧**：这些官方材料里反复写明的产品形态与用例（如客服、编码、RAG、多 Agent 编排、Computer Use 等）。

### 1.2 一手来源原则

- **纳入**：`docs.*.com` / `learn.microsoft.com` / `help.aliyun.com` / 厂商 GitHub README / 官方 API 迁移说明等。
- **排除作为依据**：第三方 “Top 10 Agents” 文章、自媒体榜单、未经厂商确认的二手转述。
- **时效**：尽量采用 2025–2026 仍在维护的产品名与文档表述；若厂商已标注废弃/迁移，在文中单独说明。

### 1.3 覆盖范围

按任务清单逐一核对官方材料，并按一手文档是否充分决定详略：LangChain/LangGraph、LlamaIndex、OpenAI Agents SDK / Responses / Assistants、Anthropic（tool use / Computer Use / Claude Agent SDK）、Microsoft（Agent Framework / AutoGen / Semantic Kernel / Foundry Agent Service）、Google ADK、CrewAI、Hugging Face smolagents、阿里云百炼（DashScope 应用 API）。Cursor 等编码 Agent 产品仅作为「应用类别」提及，不作重点。

---

## 2. 框架 / SDK / 平台对照表

| 名称 | 维护方 | 官方一句话定位（摘自一手材料） | 关键文档 |
| --- | --- | --- | --- |
| **LangGraph** | LangChain Inc. | 「low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents」 | [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) |
| **LangChain**（agents 层） | LangChain Inc. | Agent framework：模型/工具/agent loop 抽象；更高层 agent 建在 LangGraph 之上 | [Frameworks, runtimes, and harnesses](https://docs.langchain.com/oss/python/concepts/products) |
| **Deep Agents** | LangChain Inc. | Agent harness：在 LangGraph 上叠加 planning、subagents、文件系统工具与上下文管理 | 同上 |
| **LlamaIndex + Workflows** | LlamaIndex | 「leading framework for building LLM-powered agents over your data with LLMs and workflows」；Workflows 为多步、事件驱动编排 | [LlamaIndex framework](https://developers.llamaindex.ai/python/framework/)；[Workflows 产品页](https://www.llamaindex.ai/workflows) |
| **OpenAI Agents SDK** | OpenAI | 「build agentic AI apps in a lightweight, easy-to-use package」；Swarm 的生产向升级；默认走 Responses API | [Agents SDK (Python)](https://openai.github.io/openai-agents-python/)；[TypeScript](https://openai.github.io/openai-agents-js/) |
| **OpenAI Responses API** | OpenAI | 面向 agentic 原语的新 API  primitive；新项目推荐使用；Assistants 的演进方向 | [Migrate to Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses) |
| **OpenAI Assistants API** | OpenAI | 早期 agent 形态（beta）；**已弃用，日落日 2026-08-26**，应迁到 Responses | [Assistants migration](https://developers.openai.com/api/docs/assistants/migration) |
| **Claude Agent SDK** | Anthropic | 提供与 Claude Code 相同的工具、agent loop 与上下文管理，可在自有进程中运行 | [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk) |
| **Claude tool use / Computer Use** | Anthropic | Tool use：模型决定何时调用工具；Computer Use：截图 + 键鼠控制桌面环境（beta） | [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)；[Computer use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool) |
| **Microsoft Agent Framework** | Microsoft | AutoGen 与 Semantic Kernel 的直接继任者：单/多 Agent + 企业特性 + 图工作流 | [Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/?pivots=programming-language-csharp) |
| **AutoGen** | Microsoft（社区维护） | GitHub 标明 **maintenance mode**；新项目应改用 Microsoft Agent Framework | [microsoft/autogen README](https://github.com/microsoft/autogen)；[迁移指南](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/) |
| **Semantic Kernel Agent Framework** | Microsoft | 在 SK 生态内创建 AI agents 并纳入 agentic 模式；含 AzureAIAgent 等类型 | [SK Agent Framework](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/) |
| **Microsoft Foundry Agent Service** | Microsoft Azure | 托管平台：Prompt agents / Hosted agents；任意框架 + Foundry 模型目录 + Responses API 入口 | [Foundry Agent Service overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)（文档标注 Last updated 2026-06-02） |
| **Google Agent Development Kit (ADK)** | Google | 「open-source agent development framework… build, debug, and deploy reliable AI agents at enterprise scale」；Python/TS/Go/Java/Kotlin | [adk.dev](https://adk.dev/)；[Cloud ADK 页](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk) |
| **CrewAI** | CrewAI Inc. | 「leading open-source framework for orchestrating autonomous AI agents and building complex workflows」（Crews + Flows） | [CrewAI Introduction](https://docs.crewai.com/en/introduction) |
| **smolagents** | Hugging Face | 「make it extremely easy to build and run agents using just a few lines of code」；强调 Code Agents | [smolagents docs](https://huggingface.co/docs/smolagents/main/en/index)；[GitHub](https://github.com/huggingface/smolagents)（README 显示最新 release v1.26.0，2026-05） |
| **阿里云百炼应用（智能体 / 工作流）+ DashScope API** | 阿里云 | 三种模式：智能体（Agent）、工作流（Workflow）、高代码；经 DashScope 调用应用 completion | [应用模式介绍](https://help.aliyun.com/zh/model-studio/application-introduction)；[DashScope 应用 API](https://help.aliyun.com/zh/model-studio/agent-and-workflow-application-api-reference) |

### 2.1 分层速览（便于对照）

官方材料里可粗分为三层（命名来自 LangChain 自家对照页，也与多家厂商表述相容）：

| 层级 | 含义 | 本表中的例子 |
| --- | --- | --- |
| **Agent framework** | 模型、工具、agent loop 等高层抽象 | LangChain、CrewAI、OpenAI Agents SDK、ADK、smolagents、LlamaIndex agents |
| **Orchestration / runtime** | 持久执行、图/事件工作流、人机回环、检查点 | LangGraph、LlamaIndex Workflows、CrewAI Flows、Agent Framework Workflows、ADK Graph Workflows |
| **Managed platform / harness** | 托管运行、沙箱、可观测、企业身份；或「开箱即用」的 coding harness | Foundry Agent Service、百炼应用、LangSmith（部署/观测）、Claude Agent SDK / Deep Agents |

依据：[LangChain products 对照](https://docs.langchain.com/oss/python/concepts/products)；[Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)；[百炼应用介绍](https://help.aliyun.com/zh/model-studio/application-introduction)。

---

## 3. 官方文档中的典型应用 / 用例分类

以下类别均在多家**官方**材料中反复出现；每条附至少一处一手引用。

### 3.1 知识增强问答 / RAG Agent

- LlamaIndex：明确列出 Question-Answering（RAG）、chatbots、文档理解与抽取；Agents 可将 RAG pipeline 作为工具之一。([LlamaIndex framework](https://developers.llamaindex.ai/python/framework/))
- 百炼智能体：知识库（RAG）连接私有数据；官方举例「客服助手」查询知识库与实时 API。([智能体应用](https://help.aliyun.com/zh/model-studio/single-agent-application))
- Foundry：内置 file search、memory、web search 等平台工具。([Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview))

### 3.2 客服 / 对话式业务助手

- 百炼：智能体适合开放式对话、智能客服；工作流文档案例含「AI 电商客服助手」。([应用模式介绍](https://help.aliyun.com/zh/model-studio/application-introduction)；[智能体应用](https://help.aliyun.com/zh/model-studio/single-agent-application))
- Foundry：Agent 可发布到 Microsoft Teams、Microsoft 365 Copilot 等用户已有工作入口。([Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview))

### 3.3 研究 / Research Agent

- Google ADK 首页示例 agent 名为 `researcher`，指令为 thorough research，并挂载 `google_search`。([adk.dev](https://adk.dev/))
- LlamaIndex：Autonomous Agents「perform research and take actions」。([LlamaIndex framework](https://developers.llamaindex.ai/python/framework/))
- CrewAI：官方用例表含「Complex Research」（Flow 管状态 → Crew 做研究）。([CrewAI Introduction](https://docs.crewai.com/en/introduction))

### 3.4 Coding / 仓库内工作区 Agent

- OpenAI Agents SDK：「Run a coding, review, or document agent inside a real isolated workspace」（Sandbox agents）。([Agents SDK](https://openai.github.io/openai-agents-python/))
- Claude Agent SDK：内置读文件、跑命令、改代码、搜代码库；quickstart 以「读代码、找 bug、修复」为例。([Agent SDK overview](https://code.claude.com/docs/en/agent-sdk)；[Quickstart](https://code.claude.com/docs/en/agent-sdk/quickstart.md))
- **应用类别备注**（非本报告重点）：Cursor 等 IDE 内 coding agent 产品属于「人机协作编码」形态，与上述 SDK 官方用例同属一类。

### 3.5 多 Agent 编排 / 团队协作

- CrewAI：Crews = 角色化自主团队；Flows = 结构化状态与控制流；生产应用建议 Flow + Crew。([CrewAI Introduction](https://docs.crewai.com/en/introduction))
- OpenAI Agents SDK：handoffs、agents-as-tools、manager-style orchestration。([Agents SDK](https://openai.github.io/openai-agents-python/))
- LangGraph：single / multi-agent / hierarchical 控制流。([LangGraph 产品页](https://www.langchain.com/langgraph)；[overview](https://docs.langchain.com/oss/python/langgraph/overview))
- Google ADK：原生 multi-agent；ADK 2.0 强调 graph-based workflows。([Cloud ADK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk)；[adk.dev](https://adk.dev/))
- Microsoft Agent Framework / Foundry Hosted agents：多 Agent 系统、自定义编排。([Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/?pivots=programming-language-csharp)；[Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/overview))

### 3.6 Browser / Computer Use / 桌面自动化

- Anthropic Computer Use：截图、鼠标、键盘，在桌面环境中自主交互（官方标注 beta）。([Computer use tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool))
- OpenAI：平台侧曾将 computer use 与 Agents SDK、Responses 一并作为构建 agents 的工具链介绍。([New tools for building agents](https://openai.com/index/new-tools-for-building-agents/))
- smolagents：提供 `webagent` CLI，支持联网搜索工具。([smolagents docs](https://huggingface.co/docs/smolagents/main/en/index))

### 3.7 语音 / Realtime Agent

- OpenAI Agents SDK：Realtime Agents（如 `gpt-realtime-2.1`）、voice pipeline（STT → agent → TTS）。([Agents SDK](https://openai.github.io/openai-agents-python/))

### 3.8 代码执行 / 沙箱内 Code Agent

- smolagents：一等公民 `CodeAgent`（用代码写动作）；沙箱执行（Modal / Blaxel / E2B / Docker）。([smolagents docs](https://huggingface.co/docs/smolagents/main/en/index))
- Foundry / OpenAI 工具目录：code interpreter 类托管工具。([Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview))

### 3.9 工作流自动化 / 后台任务（可无人值守）

- Foundry：Agent 可不经聊天界面，由系统事件触发在后台自主完成任务。([Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview))
- CrewAI：Simple Automation、Application Backend（API → Crew 生成内容 → 写库）。([CrewAI Introduction](https://docs.crewai.com/en/introduction))
- 百炼工作流：可视化节点编排固定流程（订单处理、数据分析等确定性链路）。([应用模式介绍](https://help.aliyun.com/zh/model-studio/application-introduction))
- ADK FAQ：复杂多步、可重复、少人工干预的任务结构。([adk.dev](https://adk.dev/))

### 3.10 人机回环 / 长时有状态 Agent

- LangGraph：persistence、human-in-the-loop、长时 stateful agents。([LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview))
- OpenAI Agents SDK：Human in the loop、Sessions、Sandbox 可恢复会话。([Agents SDK](https://openai.github.io/openai-agents-python/))
- LlamaIndex Workflows：human-in-the-loop、checkpoint / resume。([Workflows 介绍](https://developers.llamaindex.ai/python/llamaagents/workflows/)；[产品 FAQ](https://www.llamaindex.ai/workflows))

### 3.11 多模态 / 文件问答

- 百炼新版智能体 API：文件问答（`file_list`）、视觉理解（`image_list`）。([新版智能体 API](https://help.aliyun.com/zh/model-studio/new-agent-application-api-reference))
- smolagents：vision / video / audio 输入。([smolagents docs](https://huggingface.co/docs/smolagents/main/en/index))
- LlamaIndex：multi-modal applications。([LlamaIndex framework](https://developers.llamaindex.ai/python/framework/))

---

## 4. 对作品集 / 学习路径的简短启示（推论）

> 本节为基于上文事实的**学习建议推论**，不是厂商官方承诺。

1. **先分清「框架 vs 运行时 vs 托管平台」**  
   学一套图/事件编排（LangGraph 或 LlamaIndex Workflows / CrewAI Flows）+ 一套轻量 SDK（OpenAI Agents SDK 或 smolagents）+ 了解至少一家托管（Foundry 或百炼），比堆叠十个「Top 框架」更贴合官方分层表述。

2. **作品集可按官方用例选 2–3 个形态做深**  
   例如：RAG + 工具客服（百炼/LlamaIndex 官方主线）、多 Agent 研究流水线（CrewAI / ADK）、Coding/Sandbox agent（OpenAI Sandbox 或 Claude Agent SDK）。每类都能在官方文档找到对应措辞，便于写作品说明。

3. **注意厂商路线图，避免押在已日落 API 上**  
   OpenAI Assistants API 官方日落为 **2026-08-26**；Microsoft AutoGen 进入 maintenance mode，继任者为 Agent Framework。新练习与作品应优先 Responses + Agents SDK、Agent Framework / Foundry。

4. **与本仓库相关**  
   项目已使用阿里云百炼 / DashScope：官方路径是「控制台创建智能体或工作流 → DashScope `apps/{APP_ID}/completion`」。适合作为「托管 Agent 应用 + 自研编排」对照实验，而不是替代学习通用编排框架。

---

## 5. 来源列表

| # | 来源名称 | URL |
| --- | --- | --- |
| 1 | LangGraph overview（LangChain Docs） | https://docs.langchain.com/oss/python/langgraph/overview |
| 2 | Frameworks, runtimes, and harnesses（LangChain Docs） | https://docs.langchain.com/oss/python/concepts/products |
| 3 | LangGraph 产品页 | https://www.langchain.com/langgraph |
| 4 | LlamaIndex Python framework docs | https://developers.llamaindex.ai/python/framework/ |
| 5 | LlamaIndex Workflows 产品页 | https://www.llamaindex.ai/workflows |
| 6 | LlamaIndex Workflows 开发文档 | https://developers.llamaindex.ai/python/llamaagents/workflows/ |
| 7 | OpenAI Agents SDK（Python） | https://openai.github.io/openai-agents-python/ |
| 8 | OpenAI Agents SDK（TypeScript） | https://openai.github.io/openai-agents-js/ |
| 9 | Migrate to the Responses API | https://developers.openai.com/api/docs/guides/migrate-to-responses |
| 10 | Assistants migration guide | https://developers.openai.com/api/docs/assistants/migration |
| 11 | OpenAI: New tools for building agents | https://openai.com/index/new-tools-for-building-agents/ |
| 12 | Claude Agent SDK overview | https://code.claude.com/docs/en/agent-sdk |
| 13 | Claude Agent SDK Quickstart | https://code.claude.com/docs/en/agent-sdk/quickstart.md |
| 14 | Claude tool use overview | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview |
| 15 | Claude Computer use tool | https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool |
| 16 | Microsoft Agent Framework overview | https://learn.microsoft.com/en-us/agent-framework/overview/?pivots=programming-language-csharp |
| 17 | AutoGen → Agent Framework migration | https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/ |
| 18 | microsoft/autogen GitHub README | https://github.com/microsoft/autogen |
| 19 | Semantic Kernel Agent Framework | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/ |
| 20 | Semantic Kernel AzureAIAgent | https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-types/azure-ai-agent |
| 21 | Microsoft Foundry Agent Service overview | https://learn.microsoft.com/en-us/azure/foundry/agents/overview |
| 22 | Foundry Hosted agents | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents |
| 23 | Google ADK（adk.dev） | https://adk.dev/ |
| 24 | Google Cloud：Agent Development Kit | https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk |
| 25 | CrewAI Introduction | https://docs.crewai.com/en/introduction |
| 26 | Hugging Face smolagents docs | https://huggingface.co/docs/smolagents/main/en/index |
| 27 | huggingface/smolagents GitHub | https://github.com/huggingface/smolagents |
| 28 | 阿里云百炼：三种核心应用模式 | https://help.aliyun.com/zh/model-studio/application-introduction |
| 29 | 阿里云百炼：智能体应用 | https://help.aliyun.com/zh/model-studio/single-agent-application |
| 30 | 阿里云百炼：新版智能体应用（Agent 2.0） | https://help.aliyun.com/zh/model-studio/new-single-agent-application |
| 31 | DashScope 应用 API 参考 | https://help.aliyun.com/zh/model-studio/agent-and-workflow-application-api-reference |
| 32 | 新版智能体应用 API 参考 | https://help.aliyun.com/zh/model-studio/new-agent-application-api-reference |

---

*本文件仅作调研笔记，不修改业务代码；事实陈述均附一手 URL，第 4 节为明确标注的推论。*
