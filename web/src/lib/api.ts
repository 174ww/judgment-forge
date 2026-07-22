/**
 * 为何存在：给 UI 一个带默认 baseUrl 与 session token 的单例式客户端工厂。
 * 谁调用：各客户端组件（"use client"）在事件/轮询中取 api。
 * 调用谁：createApiClient、getSessionToken；baseUrl 来自 NEXT_PUBLIC_API_BASE_URL。
 */

import { createApiClient } from "./api/client";
import { getSessionToken } from "./session";

const DEFAULT_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";

/** 返回绑定当前会话的 API 客户端（每次调用读最新 token）。 */
export function getApi() {
  return createApiClient({
    baseUrl: DEFAULT_BASE,
    getToken: getSessionToken,
  });
}

export { ApiError } from "./api/client";
export type * from "./api/types";
