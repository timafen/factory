import { Loader2, Play, RefreshCw, Trash2 } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useVisibleInterval } from "./polling";
import { ProjectTag, useProjectName } from "./project";
import { SpeakButton } from "./Speak";

type EpicSubtask = { title: string; detail?: string; complexity?: string; status?: string; task_id?: string; started_at?: string; adopted?: boolean };
type Epic = {
  id: string;
  name: string;
  goal: string;
  status: string; // planned | start-requested | running
  repository_id?: string;   // проект, к которому относится эпик
  subtasks: EpicSubtask[];
  children: { task_id: string; title: string; complexity?: string }[];
};
type TaskLite = { id: string; title: string; state: string; created_at: string; worker_id?: string };

const STAGE_RE = /^\[auto\]\s*\[(\d+)\/(\d+)\s+([^\]]+)\]\s*(.*)$/;

/** For a subtask, find its furthest pipeline task by matching base titles. */
function subtaskProgress(sub: EpicSubtask, tasks: TaskLite[]) {
  // Only this run counts: tasks created before the subtask was (re)launched are
  // history from earlier attempts and must not be shown as current progress.
  const since = sub.started_at ? Date.parse(sub.started_at) : 0;
  let best: { stage: number; total: number; stageName: string; state: string; taskId: string; workerId: string; createdAt: string } | null = null;
  for (const t of tasks) {
    const m = STAGE_RE.exec(t.title || "");
    if (!m) continue;
    if (m[4].trim() !== sub.title.trim()) continue;
    if (since && Date.parse(t.created_at) < since - 60_000) continue;
    const stage = parseInt(m[1], 10);
    const total = parseInt(m[2], 10);
    // Последняя по времени, а не самая дальняя по номеру: после возврата на
    // доработку работа идёт назад, и «дальше» перестаёт значить «сейчас».
    const newer = !best
      || Date.parse(t.created_at) > Date.parse(best.createdAt)
      || (t.created_at === best.createdAt && stage > best.stage);
    if (newer) {
      best = { stage, total, stageName: m[3], state: t.state, taskId: t.id, workerId: t.worker_id || "", createdAt: t.created_at };
    }
  }
  return best;
}

function elapsed(since?: string): string {
  if (!since) return "";
  const ms = Date.now() - Date.parse(since);
  if (!isFinite(ms) || ms < 0) return "";
  const min = Math.floor(ms / 60000);
  if (min < 1) return "меньше минуты";
  if (min < 60) return `${min} мин`;
  return `${Math.floor(min / 60)} ч ${min % 60} мин`;
}

function stateColor(state?: string): string {
  if (state === "succeeded") return "#7ee2a8";
  if (state === "failed" || state === "cancelled") return "#ff9d9d";
  if (state === "running" || state === "preparing") return "#8ec5ff";
  return "#e0cf9f";
}

export function EpicsView({ onTask, onAnswer }: { onTask?: (id: string) => void; onAnswer?: () => void }) {
  const interval = useVisibleInterval(10_000);
  const queryClient = useQueryClient();
  const [starting, setStarting] = useState<string | null>(null);
  const projectName = useProjectName();

  const epics = useQuery({
    queryKey: ["epics"],
    queryFn: async (): Promise<Epic[]> => {
      const r = await fetch("/api/v1/epics");
      if (!r.ok) throw new Error(`epics ${r.status}`);
      return ((await r.json()).epics ?? []) as Epic[];
    },
    refetchInterval: interval,
  });

  const workers = useQuery({
    queryKey: ["epics-workers"],
    queryFn: async (): Promise<{ id: string; name: string }[]> => {
      const r = await fetch("/api/v1/workers");
      if (!r.ok) throw new Error("workers");
      return ((await r.json()).workers ?? []) as { id: string; name: string }[];
    },
    refetchInterval: interval,
  });

  const questions = useQuery({
    queryKey: ["epics-questions"],
    queryFn: async (): Promise<{ id: string; task_id: string; status: string; question?: string }[]> => {
      const r = await fetch("/api/v1/questions");
      if (!r.ok) throw new Error("questions");
      return ((await r.json()).questions ?? []) as { id: string; task_id: string; status: string; question?: string }[];
    },
    refetchInterval: interval,
  });

  // Итог этапа. Успешно отработавший агент мог вернуть работу назад —
  // без вердикта экран этого не знает и говорит «готово».
  const verdicts = useQuery({
    queryKey: ["epics-verdicts"],
    queryFn: async (): Promise<Record<string, { action?: string; stage?: string }>> => {
      const r = await fetch("/api/v1/verdicts");
      if (!r.ok) throw new Error("verdicts");
      return ((await r.json()).verdicts ?? {}) as Record<string, { action?: string; stage?: string }>;
    },
    refetchInterval: interval,
  });

  const tasks = useQuery({
    queryKey: ["epics-tasks"],
    queryFn: async (): Promise<TaskLite[]> => {
      const r = await fetch("/api/v1/tasks?limit=100");
      if (!r.ok) throw new Error(`tasks ${r.status}`);
      return ((await r.json()).tasks ?? []) as TaskLite[];
    },
    refetchInterval: interval,
  });

  const remove = async (id: string, name: string) => {
    if (!window.confirm(`Удалить эпик «${name}»? Уже запущенные задачи продолжат работу.`)) return;
    await fetch(`/api/v1/epics/${id}`, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: ["epics"] });
  };

  const start = async (id: string) => {
    setStarting(id);
    try {
      await fetch(`/api/v1/epics/${id}/start`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["epics"] });
    } finally {
      setStarting(null);
    }
  };

  const workerName = (id?: string) =>
    (workers.data ?? []).find((w) => w.id === id)?.name ?? "";
  // Что этап значит для работы, человеческими словами.
  const stageOutcome = (p: { stage: number; total: number; stageName: string; state: string; taskId: string }) => {
    if (p.state === "running" || p.state === "preparing") return `${p.stageName} · идёт`;
    if (p.state === "queued") return `${p.stageName} · ждёт исполнителя`;
    if (p.state === "failed") return `${p.stageName} · сорвался`;
    if (p.state === "cancelled") return `${p.stageName} · отменён`;
    const v = (verdicts.data ?? {})[p.taskId];
    if (!v) return `${p.stageName} · закончил, решение за оркестратором`;
    if (v.action === "advance") return `${p.stageName} · пройден`;
    return p.stageName === "Review"
      ? `${p.stageName} · вернул на доработку`
      : `${p.stageName} · остановлен`;
  };

  const openQ = (taskId?: string) =>
    (questions.data ?? []).find((q) => q.task_id === taskId && q.status !== "resolved");

  const all = [...(epics.data ?? [])].reverse();
  const isArchived = (st?: string) => st === "cancelled" || st === "done" || st === "archived";
  const list = all.filter((e) => !isArchived(e.status));
  const archived = all.filter((e) => isArchived(e.status));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="epics-toolbar">
        <p style={{ color: "var(--text-muted, #8a94a6)", margin: 0, flex: 1 }}>
          Эпики — большие цели, разложенные планировщиком на подзадачи. «Старт» отправляет все
          подзадачи в конвейер; дальше прогресс обновляется сам.
        </p>
        <button className="button" onClick={() => { void epics.refetch(); void tasks.refetch(); }}>
          <RefreshCw size={15} />
        </button>
      </div>

      {epics.isPending && <div className="quiet-empty">Загружаю эпики…</div>}
      {!epics.isPending && list.length === 0 && (
        <div className="quiet-empty">
          Пока пусто. Надиктуй большую цель на вкладке Say — если она тянет на эпик, план появится здесь.
        </div>
      )}

      {!epics.isPending && list.length === 0 && archived.length > 0 && (
        <div className="quiet-empty">
          Действующих эпиков нет. Завершённые и отменённые лежат в архиве ниже.
        </div>
      )}

      {list.map((e) => {
        const statusRu = statusText(e.status);
        const speech =
          `Эпик: ${e.name}. Статус: ${statusRu}. ` +
          e.subtasks.map((s, i) => {
            const p = subtaskProgress(s, tasks.data ?? []);
            return `${i + 1}. ${s.title}. ${p ? `Этап ${p.stage} из ${p.total}, ${p.stageName}, состояние ${p.state}.` : "Ещё не начата."}`;
          }).join(" ");
        return (
          <div key={e.id} style={{ background: "var(--surface, #171b24)", border: "1px solid var(--border, #262c38)", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 16 }}>{e.name}</strong>
              <ProjectTag name={projectName(e.repository_id)} />
              <span style={{ fontSize: 12, padding: "2px 10px", borderRadius: 999, background: "#22303f", color: stateColor(e.status === "running" ? "running" : undefined) }}>
                {statusRu}
              </span>
              <span style={{ fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
                готово {e.subtasks.filter((x) => x.status === "done").length} из {e.subtasks.length}
              </span>
              <SpeakButton text={speech} label="Вслух" />
              <span style={{ flex: 1 }} />
              {e.status === "planned" && (
                <button className="button button-primary" onClick={() => void start(e.id)} disabled={starting === e.id}>
                  {starting === e.id ? <Loader2 size={15} className="spin" /> : <Play size={15} />} Старт
                </button>
              )}
              <button className="button" title="Удалить эпик" onClick={() => void remove(e.id, e.name)}>
                <Trash2 size={15} />
              </button>
            </div>
            {e.goal && <p style={{ margin: 0, color: "var(--text-muted, #8a94a6)", fontSize: 14 }}>{e.goal}</p>}

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {e.subtasks.map((s, i) => {
                const st = s.status ?? "pending";
                const p = st === "pending" ? null : subtaskProgress(s, tasks.data ?? []);
                const pct = st === "done" ? 100
                  : p ? Math.round(((p.stage - (p.state === "succeeded" ? 0 : 1)) / p.total) * 100) : 0;
                const clickable = Boolean(p?.taskId && onTask && st !== "pending");
                return (
                  <div
                    key={i}
                    onClick={() => { if (p?.taskId && onTask) onTask(p.taskId); }}
                    role={clickable ? "button" : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    onKeyDown={(ev) => { if (clickable && (ev.key === "Enter" || ev.key === " ") && p?.taskId && onTask) onTask(p.taskId); }}
                    title={clickable ? "Открыть задачу" : undefined}
                    style={{ background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: "10px 12px", cursor: clickable ? "pointer" : "default" }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                      <strong style={{ fontSize: 14 }}>{i + 1}. {s.title}{clickable ? " ›" : ""}</strong>
                      <span style={{ fontSize: 12, whiteSpace: "nowrap",
                                     color: st === "done" ? "#7ee2a8"
                                          : st === "pending" ? "var(--text-muted, #8a94a6)"
                                          : p ? stateColor(p.state) : "#8ec5ff" }}>
                        {st === "done" ? "✓ готово"
                          : st === "pending" ? (e.status === "planned" ? `сложность: ${s.complexity ?? "medium"}` : "⏳ ждёт очереди")
                          : p ? stageOutcome(p) : "запускается…"}
                      </span>
                    </div>
                    {s.adopted && st === "running" && (
                      <div style={{ marginTop: 4, fontSize: 12, color: "#c9a0ff" }}>
                        ↩︎ подхвачена: была запущена раньше, до правила очерёдности — работу не выбрасываем
                      </div>
                    )}
                    {st === "pending" && e.status !== "planned" && (
                      <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
                        начнётся после предыдущей — подзадачи идут по очереди
                      </div>
                    )}
                    {p && st !== "pending" && (
                      <div style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
                        этап {p.stage} из {p.total}
                        {workerName(p.workerId) ? ` · исполняет ${workerName(p.workerId)}` : ""}
                        {p.state === "running" || p.state === "preparing"
                          ? ` · идёт ${elapsed(p.createdAt)}`
                          : p.state === "queued" ? " · ждёт свободного воркера" : ""}
                      </div>
                    )}
                    {p && st === "running" && openQ(p.taskId) && (
                      <div
                        onClick={(ev) => { ev.stopPropagation(); onAnswer?.(); }}
                        style={{ marginTop: 6, background: "#2a2418", border: "1px solid #5a4a2a", borderRadius: 6, padding: "6px 10px", fontSize: 12, color: "#e0cf9f", cursor: "pointer" }}
                      >
                        ❓ Ждёт твоего ответа: {(openQ(p.taskId)?.question || "").slice(0, 90)} — нажми, чтобы ответить ›
                      </div>
                    )}
                    <div style={{ marginTop: 8, height: 4, borderRadius: 2, background: "#22303f", overflow: "hidden" }}>
                      <div style={{ width: `${Math.min(100, Math.max(0, pct))}%`, height: "100%", background: st === "done" ? "#7ee2a8" : p ? stateColor(p.state) : "#22303f" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {archived.length > 0 && (
        <details style={{ marginTop: 4 }}>
          <summary style={{ cursor: "pointer", color: "var(--text-muted, #8a94a6)", fontSize: 14, padding: "6px 0" }}>
            Архив — {archived.length} {archived.length === 1 ? "эпик" : "эпика(ов)"}: завершённые и отменённые
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            {archived.map((e) => (
              <div
                key={e.id}
                style={{
                  background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)",
                  borderRadius: 10, padding: "10px 14px", display: "flex", alignItems: "center",
                  gap: 10, flexWrap: "wrap", opacity: 0.75,
                }}
              >
                <span style={{ fontSize: 14 }}>{e.name}</span>
                <span style={{
                  fontSize: 11, padding: "2px 9px", borderRadius: 999,
                  background: "#22262f", color: "#8a94a6",
                }}>{statusText(e.status)}</span>
                <span style={{ fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
                  подзадач готово {e.subtasks.filter((x) => x.status === "done").length} из {e.subtasks.length}
                </span>
                <span style={{ flex: 1 }} />
                <button className="button" title="Удалить из архива" onClick={() => void remove(e.id, e.name)}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/** Состояние эпика человеческими словами. */
function statusText(status?: string): string {
  switch (status) {
    case "planned": return "ждёт подтверждения";
    case "start-requested": return "запускается…";
    case "running": return "в работе";
    case "done": return "завершён";
    case "cancelled": return "отменён";
    default: return status ?? "неизвестно";
  }
}
