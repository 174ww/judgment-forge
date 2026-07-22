"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { getSessionToken } from "@/lib/session";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    if (getSessionToken()) {
      router.replace("/projects");
    }
  }, [router]);

  return (
    <main className="page" style={{ paddingTop: "4rem" }}>
      <h1>研判工坊</h1>
      <p className="lede">
        上传材料包，跑通带 HITL 闸门的多智能体研判，留下可引用的决策备忘录与 Run Trace。
      </p>
      <div className="row">
        <Link className="btn" href="/register">
          注册并开始
        </Link>
        <Link className="btn btn-secondary" href="/login">
          已有账号登录
        </Link>
      </div>
    </main>
  );
}
