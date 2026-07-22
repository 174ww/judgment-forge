"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/RequireAuth";
import { ApiError, getApi } from "@/lib/api";
import type { Material, Project } from "@/lib/api/types";
import { listRecentRuns, rememberRun, type RecentRunRef } from "@/lib/recent-runs";

function ProjectDetail() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [recent, setRecent] = useState<RecentRunRef[]>([]);
  const [question, setQuestion] = useState(
    "Should an individual/small team self-build agent orchestration (LangGraph-class) or ship first on a managed agent (e.g. 百炼)?",
  );
  const [produceChecklist, setProduceChecklist] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busyRun, setBusyRun] = useState(false);

  const readyCount = materials.filter((m) => m.status === "ready").length;
  const processing = materials.some((m) => m.status === "processing");
  const canStartRun = readyCount > 0 && !busyRun;

  const refresh = useCallback(async () => {
    const api = getApi();
    try {
      const [p, mats] = await Promise.all([
        api.getProject(projectId),
        api.listMaterials(projectId),
      ]);
      setProject(p);
      setMaterials(mats);
      setRecent(listRecentRuns(projectId));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载项目失败");
    }
  }, [projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!processing) return;
    const id = setInterval(() => {
      void refresh();
    }, 1500);
    return () => clearInterval(id);
  }, [processing, refresh]);

  async function onUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const input = form.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    setBusyUpload(true);
    setError(null);
    try {
      await getApi().uploadMaterial(projectId, file);
      input.value = "";
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传失败");
    } finally {
      setBusyUpload(false);
    }
  }

  async function onDeleteMaterial(materialId: string) {
    setError(null);
    try {
      await getApi().deleteMaterial(projectId, materialId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function onStartRun(e: FormEvent) {
    e.preventDefault();
    setBusyRun(true);
    setError(null);
    try {
      const run = await getApi().startRun(
        projectId,
        question.trim(),
        produceChecklist,
      );
      rememberRun(projectId, { id: run.id, question: run.question });
      router.push(`/projects/${projectId}/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "启动 run 失败");
      setBusyRun(false);
    }
  }

  if (!project && !error) {
    return (
      <main className="page">
        <p className="muted">加载项目…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <p className="muted" style={{ marginBottom: "0.5rem" }}>
        <Link href="/projects">← 项目列表</Link>
      </p>
      <h1>{project?.name ?? "项目"}</h1>
      {project?.description ? <p className="lede">{project.description}</p> : null}
      {error ? <div className="error" style={{ marginBottom: "1rem" }}>{error}</div> : null}

      <div className="split-2">
        <section className="panel">
          <h2>材料</h2>
          <form className="stack" onSubmit={onUpload} style={{ marginTop: "0.75rem" }}>
            <label className="label">
              <span>上传 PDF / Markdown / 纯文本</span>
              <input type="file" name="file" required />
            </label>
            <button className="btn" type="submit" disabled={busyUpload}>
              {busyUpload ? "上传中…" : "上传材料"}
            </button>
          </form>
          <ul className="list" style={{ marginTop: "0.75rem" }}>
            {materials.map((m) => (
              <li key={m.id}>
                <div>
                  <strong>{m.filename}</strong>
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    {m.status}
                    {m.error_message ? ` · ${m.error_message}` : ""}
                    {` · ${(m.size_bytes / 1024).toFixed(1)} KB`}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => void onDeleteMaterial(m.id)}
                >
                  删除
                </button>
              </li>
            ))}
          </ul>
          {materials.length === 0 ? (
            <p className="muted">尚未上传材料。至少上传一份再启 run。</p>
          ) : null}
        </section>

        <section className="panel">
          <h2>启动研判</h2>
          <form className="stack" onSubmit={onStartRun} style={{ marginTop: "0.75rem" }}>
            <label className="label">
              <span>研判问题</span>
              <textarea
                required
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <label className="row" style={{ color: "var(--ink-muted)", fontSize: "0.9rem" }}>
              <input
                type="checkbox"
                checked={produceChecklist}
                onChange={(e) => setProduceChecklist(e.target.checked)}
              />
              产出行动清单（需第二道 HITL 批准）
            </label>
            <button className="btn" type="submit" disabled={!canStartRun}>
              {busyRun
                ? "启动中…"
                : readyCount === 0
                  ? "需至少一份 ready 材料"
                  : processing
                    ? "开始 Run（仍有材料处理中）"
                    : "开始 Run"}
            </button>
            {readyCount === 0 ? (
              <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
                上传并等待材料变为 ready 后再启 run。
                {processing ? " 入库中，自动刷新…" : ""}
              </p>
            ) : null}          </form>
        </section>
      </div>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>最近 Runs</h2>
        {recent.length === 0 ? (
          <p className="muted" style={{ marginTop: "0.5rem" }}>
            本机尚无记录。启动后会跳到 run 页，并保存在浏览器本地。
          </p>
        ) : (
          <ul className="list">
            {recent.map((r) => (
              <li key={r.id}>
                <div>
                  <Link href={`/projects/${projectId}/runs/${r.id}`}>{r.question}</Link>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {r.id.slice(0, 8)}… · {new Date(r.savedAt).toLocaleString()}
                  </div>
                </div>
                <Link href={`/projects/${projectId}/runs/${r.id}`}>打开</Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

export default function ProjectPage() {
  return (
    <RequireAuth>
      <ProjectDetail />
    </RequireAuth>
  );
}
