export function stageHandoffTargetStatus(completedWorks: number, minimumSample: number, met: boolean | null) {
  if (completedWorks < minimumSample || met == null) return { text: "данных мало", tone: "muted" as const };
  return met ? { text: "цель достигнута", tone: "ok" as const } : { text: "цель не достигнута", tone: "bad" as const };
}
