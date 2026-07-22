/**
 * 为何存在：把 FastAPI 响应形状收敛成前端可引用的 TypeScript 类型，避免页面散落 magic string。
 * 谁调用：api/client 与各 workbench 页面/组件。
 * 调用谁：无运行时依赖（纯类型）。
 */

export type User = {
  id: string;
  email: string;
};

export type TokenResponse = {
  token: string;
  token_type: string;
  user: User;
};

export type Project = {
  id: string;
  name: string;
  description: string;
  archived: boolean;
};

export type Material = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "processing" | "ready" | "failed" | string;
  error_message: string | null;
};

export type HitlGate = "web" | "checklist";
export type HitlDecision = "approve" | "deny";

export type RunStatus =
  | "queued"
  | "running"
  | "waiting_for_human"
  | "completed"
  | "failed"
  | "cancelled"
  | string;

export type JudgmentRun = {
  id: string;
  project_id: string;
  question: string;
  produce_checklist: boolean;
  web_enabled: boolean;
  status: RunStatus;
  error_message: string | null;
  critic_bounce_count: number;
  pending_hitl: Record<string, unknown> | null;
  hitl_events: Record<string, unknown>[];
};

export type MemoClaimAnchor = {
  material_id: string | null;
  location_hint: string | null;
  url: string | null;
  retrieved_at: string | null;
};

export type MemoClaim = {
  text: string;
  presented_as: string;
  anchors: MemoClaimAnchor[];
};

export type DecisionMemo = {
  conclusion: string;
  options: string;
  risks_unknowns: string;
  next_steps: string;
  claims: MemoClaim[];
  checklist: string[] | null;
};

export type TraceEventsResponse = {
  events: Record<string, unknown>[];
};
