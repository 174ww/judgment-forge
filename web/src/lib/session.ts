/**
 * 为何存在：会话 token / 用户快照的浏览器持久化，让刷新后仍能带鉴权调 API。
 * 谁调用：api 入口工厂、登录/登出页、需鉴权的布局守卫。
 * 调用谁：localStorage（仅浏览器）；不直接打 HTTP。
 */

import type { User } from "./api/types";

const TOKEN_KEY = "judgment_forge_token";
const USER_KEY = "judgment_forge_user";

/** 读取当前 Bearer token；无会话或非浏览器环境返回 null。 */
export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

/** 读取缓存的当前用户；仅作 UI 展示，权威身份以 /auth/me 为准。 */
export function getSessionUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

/** 登录成功后写入 token 与用户快照。 */
export function setSession(token: string, user: User): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/** 登出或 401 时清空本地会话。 */
export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}
