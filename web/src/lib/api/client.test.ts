/**
 * 为何存在：验收薄 API 客户端缝（createApiClient）的公开 HTTP 行为，不测 React。
 * 谁调用：vitest（npm test / web package）。
 * 调用谁：createApiClient / ApiError；用假 fetch Response 验证鉴权头、路径与错误映射。
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createApiClient", () => {
  it("login returns token and user from /auth/login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        token: "sess-1",
        token_type: "bearer",
        user: { id: "u1", email: "a@example.com" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = createApiClient({
      baseUrl: "http://api.test",
      getToken: () => null,
    });
    const result = await api.login("a@example.com", "password1");

    expect(result.token).toBe("sess-1");
    expect(result.user.email).toBe("a@example.com");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/auth/login",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("authenticated calls send Bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([{ id: "p1", name: "Demo", description: "", archived: false }]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = createApiClient({
      baseUrl: "http://api.test",
      getToken: () => "tok-abc",
    });
    await api.listProjects();

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok-abc");
  });

  it("maps non-OK JSON detail into ApiError", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ detail: "invalid email or password" }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = createApiClient({
      baseUrl: "http://api.test",
      getToken: () => null,
    });

    await expect(api.login("x@y.com", "bad")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "invalid email or password",
    } satisfies Partial<ApiError>);
  });

  it("decideHitl posts gate and decision", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "r1",
        project_id: "p1",
        question: "q",
        produce_checklist: true,
        web_enabled: true,
        status: "running",
        error_message: null,
        critic_bounce_count: 0,
        pending_hitl: null,
        hitl_events: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const api = createApiClient({
      baseUrl: "http://api.test",
      getToken: () => "tok",
    });
    await api.decideHitl("p1", "r1", "web", "approve");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/projects/p1/runs/r1/hitl",
      expect.objectContaining({ method: "POST" }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      gate: "web",
      decision: "approve",
    });
  });
});
