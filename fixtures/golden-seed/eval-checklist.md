# 评测清单（v1，3–5 条）

固定场景，便于面试/验收讨论质量，**不是**完整 ML eval 平台。每条写清预期信号。

## 1. 金路径：自建编排 vs 托管 Agent

- **输入**：本种子包材料 + 金问题（见 `README.md`）。
- **操作**：启 run；联网闸可拒绝（材料足够时）；若勾选清单则在清单闸批/拒其一。
- **预期**：完成后有决策备忘录；结论能对照 framework / runtime / managed 分层叙事。

## 2. 材料主张带锚点（anchors）

- **输入**：同上，备忘录中引用 landscape 或摘录中的事实句。
- **预期**：材料来源的事实句带 citation anchor（文档 id + 页/段位置提示）；无锚点句子应标为「推断/未知」，不得伪装成已证实事实。

## 3. Critic 打回可见（critic bounce）

- **固定复现（API / FakeLLM）**：跑 `api/tests/test_run_trace.py::test_owner_can_fetch_ordered_trace_with_hitl_and_critic_bounce`（夹具图首轮故意无锚点 fact → Critic bounce）。
- **预期**：Trace 含 `kind=critic_bounce`，且 `critic_bounce_count >= 1`。
- **演示口述**：打开完成后的 Run Trace，指出 bounce 事件，解释 Critic → Researcher 回路。

## 4. 无意外联网（web gate）

- **输入**：新 run，默认 web 关闭；在 HITL 联网闸选择**拒绝**（金路径演示脚本同此）。
- **预期**：批准前无 web/search 工具调用；拒绝后仍可仅凭材料包完成备忘录。
- **固定复现（API）**：见 `api/tests/test_hitl_web_gate.py` 拒网路径。

## 5. 清单闸与取消（可选第五条）

- **清单**：`produce_checklist=true` 时，Writer 后出现清单 HITL；拒绝后仍应有备忘录、无定稿清单（`test_checklist_hitl.py`）。
- **取消**：running / waiting_for_human 时可取消；状态为 `cancelled`（`test_cancel_resume_hitl.py`）。
