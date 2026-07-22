import type { JudgmentRun } from "@/lib/api/types";

export function statusBadgeClass(status: string): string {
  if (status === "waiting_for_human") return "badge badge-warn";
  if (status === "failed" || status === "cancelled") return "badge badge-danger";
  if (status === "completed") return "badge";
  return "badge badge-muted";
}

export function StatusBadge({ run }: { run: Pick<JudgmentRun, "status"> }) {
  return <span className={statusBadgeClass(run.status)}>{run.status}</span>;
}

export function pendingGate(run: JudgmentRun): "web" | "checklist" | null {
  const pending = run.pending_hitl;
  if (!pending || run.status !== "waiting_for_human") return null;
  const gate = pending.gate;
  if (gate === "web" || gate === "checklist") return gate;
  return null;
}
