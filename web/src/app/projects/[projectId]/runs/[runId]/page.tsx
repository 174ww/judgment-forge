"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { RequireAuth } from "@/components/RequireAuth";
import { StatusBadge, pendingGate } from "@/components/run-helpers";
import { ApiError, getApi } from "@/lib/api";
import type {
  DecisionMemo,
  HitlDecision,
  HitlGate,
  JudgmentRun,
} from "@/lib/api/types";

const ACTIVE = new Set(["queued", "running", "waiting_for_human"]);
const POLL_MS = 1500;

function formatTraceEvent(ev: Record<string, unknown>): string {
  const seq = ev.seq ?? "?";
  const kind = ev.kind ?? ev.type ?? "event";
  const node = ev.node ?? ev.agent ?? "";
  const gate = ev.gate ? ` gate=${ev.gate}` : "";
  const decision = ev.decision ? ` decision=${ev.decision}` : "";
  const tool = ev.tool ? ` tool=${ev.tool}` : "";
  const tokens =
    ev.token_estimate != null ? ` tokens≈${ev.token_estimate}` : "";
  const latency =
    ev.latency_ms != null ? ` ${ev.latency_ms}ms` : "";
  return `#${seq} ${kind}${node ? ` · ${node}` : ""}${tool}${gate}${decision}${tokens}${latency}`;
}

function RunWorkbench() {
  const params = useParams<{ projectId: string; runId: string }>();
  const { projectId, runId } = params;

  const [run, setRun] = useState<JudgmentRun | null>(null);
  const [memo, setMemo] = useState<DecisionMemo | null>(null);
  const [trace, setTrace] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hitlBusy, setHitlBusy] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadArtifacts = useCallback(
    async (status: string) => {
      const api = getApi();
      try {
        const tr = await api.getTrace(projectId, runId);
        setTrace(tr.events ?? []);
      } catch {
        /* trace 可能在早期为空；忽略 */
      }
      if (status === "completed") {
        try {
          setMemo(await api.getMemo(projectId, runId));
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "读取备忘录失败");
        }
      }
    },
    [projectId, runId],
  );

  const refresh = useCallback(async () => {
    try {
      const next = await getApi().getRun(projectId, runId);
      setRun(next);
      setError(null);
      await loadArtifacts(next.status);
      return next;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载 run 失败");
      return null;
    }
  }, [loadArtifacts, projectId, runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!run || !ACTIVE.has(run.status)) return;

    pollRef.current = setInterval(() => {
      void refresh();
    }, POLL_MS);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [run?.status, refresh, run]);

  async function onHitl(gate: HitlGate, decision: HitlDecision) {
    setHitlBusy(true);
    setError(null);
    try {
      const next = await getApi().decideHitl(projectId, runId, gate, decision);
      setRun(next);
      await loadArtifacts(next.status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "提交 HITL 失败");
    } finally {
      setHitlBusy(false);
    }
  }

  async function onCancel() {
    setCancelBusy(true);
    setError(null);
    try {
      const next = await getApi().cancelRun(projectId, runId);
      setRun(next);
      await loadArtifacts(next.status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "取消失败");
    } finally {
      setCancelBusy(false);
    }
  }

  const gate = run ? pendingGate(run) : null;

  if (!run && !error) {
    return (
      <main className="page">
        <p className="muted">加载 run…</p>
      </main>
    );
  }

  return (
    <main className="page">
      <p className="muted" style={{ marginBottom: "0.5rem" }}>
        <Link href={`/projects/${projectId}`}>← 返回项目</Link>
      </p>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>研判 Run</h1>
          <p className="lede" style={{ marginBottom: 0 }}>
            {run?.question}
          </p>
        </div>
        {run ? <StatusBadge run={run} /> : null}
      </div>

      {error ? (
        <div className="error" style={{ margin: "1rem 0" }}>
          {error}
        </div>
      ) : null}

      {run ? (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div className="muted" style={{ fontSize: "0.9rem" }}>
              id {run.id}
              {" · "}
              checklist opt-in: {run.produce_checklist ? "yes" : "no"}
              {" · "}
              web: {run.web_enabled ? "on" : "off"}
              {" · "}
              critic bounces: {run.critic_bounce_count}
              {ACTIVE.has(run.status) ? " · 轮询中…" : ""}
            </div>
            {ACTIVE.has(run.status) ? (
              <button
                type="button"
                className="btn btn-danger"
                disabled={cancelBusy}
                onClick={() => void onCancel()}
              >
                {cancelBusy ? "取消中…" : "取消 Run"}
              </button>
            ) : null}
          </div>
          {run.error_message ? (
            <p className="error" style={{ marginTop: "0.75rem" }}>
              {run.error_message}
            </p>
          ) : null}
        </section>
      ) : null}

      {gate ? (
        <section className="hitl-box" style={{ marginTop: "1rem" }}>
          <h2>
            需要人工决定 · {gate === "web" ? "联网搜索闸门" : "行动清单闸门"}
          </h2>
          <p className="lede" style={{ marginBottom: "0.85rem" }}>
            {gate === "web"
              ? "批准后 Researcher 可使用联网搜索；拒绝则仅用材料包继续。"
              : "批准后备忘录将附带 3–8 条行动清单；拒绝则只保留备忘录。"}
          </p>
          <div className="row">
            <button
              type="button"
              className="btn"
              disabled={hitlBusy}
              onClick={() => void onHitl(gate, "approve")}
            >
              批准
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={hitlBusy}
              onClick={() => void onHitl(gate, "deny")}
            >
              拒绝
            </button>
          </div>
        </section>
      ) : null}

      {run?.status === "waiting_for_human" && !gate ? (
        <section className="hitl-box" style={{ marginTop: "1rem" }}>
          <h2>需要人工决定</h2>
          <p className="lede" style={{ marginBottom: "0.85rem" }}>
            Run 在等待人机闸门，但 pending_hitl.gate 无法识别。可尝试按联网闸提交，或取消本 run。
          </p>
          <div className="row">
            <button
              type="button"
              className="btn"
              disabled={hitlBusy}
              onClick={() => void onHitl("web", "approve")}
            >
              批准（web）
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={hitlBusy}
              onClick={() => void onHitl("web", "deny")}
            >
              拒绝（web）
            </button>
          </div>
        </section>
      ) : null}

      {memo ? (
        <section className="panel" style={{ marginTop: "1rem" }}>
          <h2>决策备忘录</h2>
          <div className="memo-grid" style={{ marginTop: "0.75rem" }}>
            <div className="memo-block">
              <h3>结论</h3>
              <p>{memo.conclusion}</p>
            </div>
            <div className="memo-block">
              <h3>方案比较</h3>
              <p>{memo.options}</p>
            </div>
            <div className="memo-block">
              <h3>风险与未知</h3>
              <p>{memo.risks_unknowns}</p>
            </div>
            <div className="memo-block">
              <h3>建议下一步</h3>
              <p>{memo.next_steps}</p>
            </div>
            {memo.checklist && memo.checklist.length > 0 ? (
              <div className="memo-block">
                <h3>行动清单</h3>
                <ol className="checklist">
                  {memo.checklist.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </div>
            ) : (
              <p className="muted">本 run 无行动清单（未 opt-in 或闸门拒绝）。</p>
            )}
            <div className="memo-block">
              <h3>主张与锚点</h3>
              <ul className="list">
                {memo.claims.map((c, i) => (
                  <li key={`${i}-${c.text.slice(0, 24)}`}>
                    <div>
                      <div>{c.text}</div>
                      <div className="muted" style={{ fontSize: "0.82rem" }}>
                        presented_as={c.presented_as}
                        {c.anchors.length
                          ? ` · anchors=${c.anchors
                              .map((a) =>
                                [
                                  a.material_id,
                                  a.location_hint,
                                  a.url,
                                  a.retrieved_at,
                                ]
                                  .filter(Boolean)
                                  .join("/"),
                              )
                              .join("; ")}`
                          : " · no anchors"}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      ) : null}

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>Run Trace</h2>
        <p className="muted" style={{ margin: "0.35rem 0 0.75rem" }}>
          有序时间线（节点 / 工具 / LLM / HITL / critic bounce）。
        </p>
        {trace.length === 0 ? (
          <p className="muted">尚无事件。</p>
        ) : (
          <div className="trace">
            {trace.map((ev, i) => (
              <div className="trace-item" key={String(ev.seq ?? i)}>
                {formatTraceEvent(ev)}
              </div>
            ))}          </div>
        )}
      </section>
    </main>
  );
}

export default function RunPage() {
  return (
    <RequireAuth>
      <RunWorkbench />
    </RequireAuth>
  );
}
