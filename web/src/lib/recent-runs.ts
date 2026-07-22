/**
 * 为何存在：在无服务端 list-runs 的情况下，记住项目内最近启动的 run id，便于回访。
 * 谁调用：项目页启动 run 后写入；项目页展示「最近 runs」时读取。
 * 调用谁：localStorage。
 */

const PREFIX = "judgment_forge_recent_runs:";

export type RecentRunRef = {
  id: string;
  question: string;
  savedAt: string;
};

/** 读取某项目最近 run 列表（新在前）。 */
export function listRecentRuns(projectId: string): RecentRunRef[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(PREFIX + projectId);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as RecentRunRef[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** 把一次新启动的 run 插到列表头部，最多保留 20 条。 */
export function rememberRun(
  projectId: string,
  run: { id: string; question: string },
): void {
  const next: RecentRunRef[] = [
    { id: run.id, question: run.question, savedAt: new Date().toISOString() },
    ...listRecentRuns(projectId).filter((r) => r.id !== run.id),
  ].slice(0, 20);
  window.localStorage.setItem(PREFIX + projectId, JSON.stringify(next));
}
