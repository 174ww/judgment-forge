"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, getApi } from "@/lib/api";
import { setSession } from "@/lib/session";

export default function RegisterPage() {
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
      const api = getApi();
      await api.register(email.trim(), password);
      const result = await api.login(email.trim(), password);
      setSession(result.token, result.user);
      router.push("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page page-narrow">
      <h1>注册</h1>
      <p className="lede">创建个人账号；项目与材料按所有者隔离。</p>
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
          <span>密码（至少 8 位）</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "注册中…" : "注册并进入"}
        </button>
      </form>
      <p className="muted" style={{ marginTop: "1rem" }}>
        已有账号？<Link href="/login">登录</Link>
      </p>
    </main>
  );
}
