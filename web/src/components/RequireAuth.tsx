"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getSessionToken } from "@/lib/session";

/** 无会话则跳登录；有会话则渲染子树。 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getSessionToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <main className="page">
        <p className="muted">检查登录状态…</p>
      </main>
    );
  }

  return <>{children}</>;
}
