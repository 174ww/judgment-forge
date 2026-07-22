# 官方摘录（短）：阿里云百炼应用模式

> **用途**：金路径种子材料，对照「托管 Agent / 工作流」一侧。  
> **来源标注**：基于阿里云帮助中心一手文档的简短转述。

## 三种核心应用模式

百炼（模型工作室）官方将应用分为：

1. **智能体（Agent）**：适合开放式对话、工具调用与知识库（RAG）等场景。
2. **工作流（Workflow）**：可视化节点编排更偏确定性链路（如订单处理、数据分析）。
3. **高代码**：在托管能力之外用代码扩展。

调用侧常见路径：控制台创建智能体或工作流后，经 **DashScope 应用 API**（`apps/{APP_ID}/completion` 一类）发起 completion。

## 与金问题的关系

若小团队优先「尽快上线对话/工作流应用」，托管平台可缩短运维与观测成本；若需要一等公民的图编排、自有 HITL 闸门与一等 Run Trace，则更贴近自建 **LangGraph 类 runtime**。两者不是互相否定，而是 **framework / runtime / managed platform** 分层上的不同落点。

## 一手链接

- [应用模式介绍](https://help.aliyun.com/zh/model-studio/application-introduction)
- [智能体应用](https://help.aliyun.com/zh/model-studio/single-agent-application)
- [DashScope 应用 API 参考](https://help.aliyun.com/zh/model-studio/agent-and-workflow-application-api-reference)
