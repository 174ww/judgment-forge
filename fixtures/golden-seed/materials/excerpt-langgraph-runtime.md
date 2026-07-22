# 官方摘录（短）：LangGraph 作为编排 / 运行时

> **用途**：金路径种子材料。短摘录便于备忘录锚点演示；完整对照见同包 `agent-dev-landscape.md`。  
> **来源标注**：以下为基于一手文档的简短转述，非厂商全文授权复制。

## 定位（orchestration / runtime）

LangGraph 被官方描述为面向构建、管理与部署**长时、有状态 Agent** 的底层编排框架与运行时（low-level orchestration framework and runtime）。

关键能力表述（与本产品闸门叙事相关）：

- **持久化 / checkpoint**：长时运行状态可恢复，而非单次请求超时即丢失。
- **人机回环（human-in-the-loop）**：图执行可在关键点暂停，等待人工决策后再继续。
- **多 Agent / 图控制流**：支持 single / multi-agent / hierarchical 等编排形态。

## 分层提醒

在「Agent framework vs orchestration/runtime vs managed platform」三分法中，LangGraph 主要落在 **orchestration / runtime** 一层，而不是托管控制台本身。

## 一手链接

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [Frameworks, runtimes, and harnesses](https://docs.langchain.com/oss/python/concepts/products)
