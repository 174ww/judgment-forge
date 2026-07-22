/**
 * 为何存在：研判工坊浏览器侧的薄 HTTP 客户端——金路径 UI 只通过本模块谈 API，不散落 fetch。
 * 谁调用：登录/项目/材料/run 等页面与轮询逻辑；client.test.ts 以假 fetch 测本缝。
 * 调用谁：全局 fetch；类型见 ./types；鉴权 token 由调用方经 getToken 注入（通常来自 session）。
 */

import type {
  DecisionMemo,
  HitlDecision,
  HitlGate,
  JudgmentRun,
  Material,
  Project,
  TokenResponse,
  TraceEventsResponse,
  User,
} from "./types";

export type ApiClientOptions = {
  /** API 根，如 http://localhost:8000；末尾斜杠会被去掉。 */
  baseUrl: string;
  /** 返回当前 Bearer token；匿名操作为 null。 */
  getToken: () => string | null;
};

/** HTTP 非 2xx 时抛出；status/detail 供 UI 展示。 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function joinUrl(baseUrl: string, path: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail: unknown }).detail;
    if (typeof inner === "string" && inner.trim()) return inner;
  }
  return fallback;
}

/**
 * 构造面向 JudgmentForge HTTP 缝的客户端。
 * 控制流：拼 URL → 可选 Authorization → fetch → 非 OK 抛 ApiError → 解析 JSON/空体。
 */
export function createApiClient(options: ApiClientOptions) {
  const { baseUrl, getToken } = options;

  async function request<T>(
    path: string,
    init: RequestInit = {},
    parse: "json" | "empty" = "json",
  ): Promise<T> {
    const headers = new Headers(init.headers);
    const token = getToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(joinUrl(baseUrl, path), {
      ...init,
      headers,
    });

    if (!response.ok) {
      let detail: unknown = null;
      const text = await response.text();
      if (text) {
        try {
          detail = JSON.parse(text);
        } catch {
          detail = text;
        }
      }
      throw new ApiError(
        response.status,
        detailMessage(detail, response.statusText || `HTTP ${response.status}`),
        detail,
      );
    }

    if (parse === "empty" || response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  return {
    /** POST /auth/register → 用户（不含 token，需再 login）。 */
    register(email: string, password: string): Promise<User> {
      return request<User>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
    },

    /** POST /auth/login → token + user。 */
    login(email: string, password: string): Promise<TokenResponse> {
      return request<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
    },

    /** POST /auth/logout；失败时仍由调用方清本地会话。 */
    logout(): Promise<void> {
      return request<void>("/auth/logout", { method: "POST" }, "empty");
    },

    /** GET /auth/me：探测当前会话对应用户。 */
    me(): Promise<User> {
      return request<User>("/auth/me");
    },

    /** GET /projects：当前所有者的项目列表。 */
    listProjects(): Promise<Project[]> {
      return request<Project[]>("/projects");
    },

    /** POST /projects：创建项目。 */
    createProject(name: string, description = ""): Promise<Project> {
      return request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      });
    },

    /** GET /projects/{id}：读单个项目（跨用户 → 404）。 */
    getProject(projectId: string): Promise<Project> {
      return request<Project>(`/projects/${projectId}`);
    },

    /** GET .../materials：列出项目材料及入库状态。 */
    listMaterials(projectId: string): Promise<Material[]> {
      return request<Material[]>(`/projects/${projectId}/materials`);
    },

    /** multipart 上传；勿手动设 Content-Type，让浏览器带 boundary。 */
    uploadMaterial(projectId: string, file: File): Promise<Material> {
      const body = new FormData();
      body.append("file", file);
      return request<Material>(`/projects/${projectId}/materials`, {
        method: "POST",
        body,
      });
    },

    /** DELETE 材料；删除后检索不再命中其 chunks。 */
    deleteMaterial(projectId: string, materialId: string): Promise<void> {
      return request<void>(
        `/projects/${projectId}/materials/${materialId}`,
        { method: "DELETE" },
        "empty",
      );
    },

    /** POST .../runs：启动研判；可带 produce_checklist。 */
    startRun(
      projectId: string,
      question: string,
      produceChecklist = false,
    ): Promise<JudgmentRun> {
      return request<JudgmentRun>(`/projects/${projectId}/runs`, {
        method: "POST",
        body: JSON.stringify({
          question,
          produce_checklist: produceChecklist,
        }),
      });
    },

    /** GET run 状态（含 pending_hitl / hitl_events）。 */
    getRun(projectId: string, runId: string): Promise<JudgmentRun> {
      return request<JudgmentRun>(`/projects/${projectId}/runs/${runId}`);
    },

    /** POST HITL 决定并 resume 检查点（gate=web|checklist）。 */
    decideHitl(
      projectId: string,
      runId: string,
      gate: HitlGate,
      decision: HitlDecision,
    ): Promise<JudgmentRun> {
      return request<JudgmentRun>(`/projects/${projectId}/runs/${runId}/hitl`, {
        method: "POST",
        body: JSON.stringify({ gate, decision }),
      });
    },

    /** POST 取消进行中的 run → cancelled。 */
    cancelRun(projectId: string, runId: string): Promise<JudgmentRun> {
      return request<JudgmentRun>(`/projects/${projectId}/runs/${runId}/cancel`, {
        method: "POST",
      });
    },

    /** GET 决策备忘录（含可选 checklist）。 */
    getMemo(projectId: string, runId: string): Promise<DecisionMemo> {
      return request<DecisionMemo>(`/projects/${projectId}/runs/${runId}/memo`);
    },

    /** GET 有序 Run Trace 时间线。 */
    getTrace(projectId: string, runId: string): Promise<TraceEventsResponse> {
      return request<TraceEventsResponse>(
        `/projects/${projectId}/runs/${runId}/trace`,
      );
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
