"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, getApi } from "@/lib/api";
import type { Project } from "@/lib/api/types";

function ProjectsWorkbench() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setProjects(await getApi().listProjects());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载项目失败");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await getApi().createProject(name.trim(), description.trim());
      setName("");
      setDescription("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page">
      <h1>我的项目</h1>
      <p className="lede">每个项目承载材料包与研判 runs；仅你本人可见。</p>

      <section className="panel">
        <h2>新建项目</h2>
        <form className="stack" onSubmit={onCreate} style={{ marginTop: "0.75rem" }}>
          <label className="label">
            <span>名称</span>
            <input
              type="text"
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="label">
            <span>描述（可选）</span>
            <textarea
              maxLength={4000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {error ? <div className="error">{error}</div> : null}
          <div className="row">
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "创建中…" : "创建项目"}
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <h2>项目列表</h2>
        {projects.length === 0 ? (
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            还没有项目。先创建一个再上传材料。
          </p>
        ) : (
          <ul className="list">
            {projects.map((p) => (
              <li key={p.id}>
                <div>
                  <Link href={`/projects/${p.id}`}>{p.name}</Link>
                  {p.archived ? (
                    <span className="badge badge-muted" style={{ marginLeft: "0.5rem" }}>
                      archived
                    </span>
                  ) : null}
                  {p.description ? (
                    <div className="muted" style={{ marginTop: "0.25rem", fontSize: "0.9rem" }}>
                      {p.description}
                    </div>
                  ) : null}
                </div>
                <Link href={`/projects/${p.id}`}>打开</Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default function ProjectsPage() {
  return (
    <RequireAuth>
      <ProjectsWorkbench />
    </RequireAuth>
  );
}
