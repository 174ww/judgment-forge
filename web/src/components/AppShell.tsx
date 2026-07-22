"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getApi } from "@/lib/api";
import { clearSession, getSessionUser } from "@/lib/session";
import type { User } from "@/lib/api/types";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setUser(getSessionUser());
  }, [pathname]);

  async function onLogout() {
    try {
      await getApi().logout();
    } catch {
      /* 本地仍清会话 */
    }
    clearSession();
    setUser(null);
    router.push("/login");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link href={user ? "/projects" : "/"} className="brand">
          研判工坊
          <span>judgment-forge</span>
        </Link>
        <div className="topbar-actions">
          {user ? (
            <>
              <span>{user.email}</span>
              <Link href="/projects">项目</Link>
              <button type="button" className="btn btn-ghost" onClick={onLogout}>
                登出
              </button>
            </>
          ) : (
            <>
              <Link href="/login">登录</Link>
              <Link href="/register">注册</Link>
            </>
          )}
        </div>
      </header>
      {children}
    </div>
  );
}
