"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, getApi } from "@/lib/api";
import { setSession } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await getApi().login(email.trim(), password);
      setSession(result.token, result.user);
      router.push("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page page-narrow">
      <h1>登录</h1>
      <p className="lede">使用邮箱与密码进入工作台。</p>
      <form className="panel stack" onSubmit={onSubmit}>
        <label className="label">
          <span>邮箱</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="label">
          <span>密码</span>
          <input
            type="password"
            required
            minLength={1}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
      <p className="muted" style={{ marginTop: "1rem" }}>
        还没有账号？<Link href="/register">注册</Link>
      </p>
    </main>
  );
}
