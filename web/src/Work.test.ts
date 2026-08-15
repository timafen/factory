import { describe, expect, it } from "vitest";
import { build, sectionOf } from "./Work";
import type { Task } from "./types";

function task(id: string, stage: string, state: Task["state"], minute: number, workID?: string): Task {
  return {
    id,
    work_id: workID,
    title: `[auto] [3/5 ${stage}] Экран Работа`,
    state,
    created_at: `2026-08-08T10:${String(minute).padStart(2, "0")}:00Z`,
  } as Task;
}

describe("build", () => {
  it("groups stage titles by work identity and keeps equal names separate", () => {
    const sharedWork = build([
      task("triage", "Triage", "succeeded", 1, "work-shared"),
      { ...task("specification", "Specification", "running", 2, "work-shared"),
        title: "[auto] [2/5 Specification] Уточнённое название" },
    ], {}, []);
    const equalNames = build([
      task("first", "Triage", "running", 1, "work-first"),
      task("second", "Triage", "running", 2, "work-second"),
    ], {}, []);
    const legacy = build([
      task("legacy-triage", "Triage", "succeeded", 1),
      task("legacy-specification", "Specification", "running", 2),
    ], {}, []);

    expect(sharedWork).toHaveLength(1);
    expect(sharedWork[0]).toMatchObject({ id: "work-shared", base: "Экран Работа" });
    expect(sharedWork[0].items).toHaveLength(2);
    expect(equalNames.map((group) => group.id)).toEqual(["work-second", "work-first"]);
    expect(legacy).toHaveLength(1);
    expect(legacy[0]).toMatchObject({ id: "Экран Работа", base: "Экран Работа" });
  });

  it("looks up work metadata by identity before the legacy title fallback", () => {
    const [group] = build([task("paused", "Review", "failed", 1, "work-paused")], {}, [], {
      "work-paused": { origin: "owner" },
      "Экран Работа": { origin: "assistant" },
    }, {
      "work-paused": { state: "stopped_owner", text: "пауза по идентификатору работы" },
    }, {
      "work-paused": { files: ["web/src/Work.tsx"] },
    });

    expect(group.meta?.origin).toBe("owner");
    expect(group.promise?.files).toEqual(["web/src/Work.tsx"]);
    expect(group.status).toMatchObject({ kind: "paused", happened: "пауза по идентификатору работы" });
  });

  it("marks the live repeated stage as again and retains later stage history", () => {
    const group = build([
      task("implement-1", "Implement + Test", "succeeded", 1),
      task("review-1", "Review", "succeeded", 2),
      task("implement-2", "Implement + Test", "running", 3),
    ], {}, [])[0];

    expect(group.currentStage).toBe("Implement + Test");
    expect(group.reached["Implement + Test"]).toBe("again");
    expect(group.reached.Review).toBe("done");
  });

  it("does not mark the first live run of a stage as again", () => {
    const group = build([
      task("specification", "Specification", "succeeded", 1),
      task("implement", "Implement + Test", "running", 2),
    ], {}, [])[0];

    expect(group.reached["Implement + Test"]).toBe("live");
  });

  it("marks a repeated first stage as again", () => {
    const group = build([
      task("triage-1", "Triage", "succeeded", 1),
      task("specification", "Specification", "succeeded", 2),
      task("triage-2", "Triage", "running", 3),
    ], {}, [])[0];

    expect(group.currentStage).toBe("Triage");
    expect(group.reached.Triage).toBe("again");
    expect(group.reached.Specification).toBe("done");
  });

  it("marks a repeated last stage as again", () => {
    const group = build([
      task("verify-1", "Verify", "succeeded", 1),
      task("review", "Review", "succeeded", 2),
      task("verify-2", "Verify", "running", 3),
    ], {}, [])[0];

    expect(group.currentStage).toBe("Verify");
    expect(group.reached.Verify).toBe("again");
    expect(group.reached.Review).toBe("done");
  });

  it("does not paint a rejected verification green", () => {
    const group = build([
      task("verify-1", "Verify", "succeeded", 1),
      task("implement-2", "Implement + Test", "running", 2),
    ], { "verify-1": { final_pass: false } }, [])[0];

    expect(group.reached.Verify).toBe("bad");
    expect(group.reached["Implement + Test"]).toBe("live");
  });

  it("keeps an active retry in work and states the real current step", () => {
    const group = build([
      task("verify", "Verify", "succeeded", 1),
      task("implement-retry", "Implement + Test", "running", 2),
    ], { verify: { final_pass: false } }, [])[0];

    expect(group.status).toMatchObject({
      kind: "repairing",
      label: "Исправляется автоматически",
      next: "Factory сейчас выполняет «Разработка».",
      owner: "Участие владельца не требуется.",
    });
  });

  it("puts an open owner question ahead of a running task", () => {
    const group = build([task("implement", "Implement + Test", "running", 1)], {}, [{
      task_id: "implement", status: "open", question: "Выбрать вариант A или B?",
    }])[0];

    expect(group.status).toMatchObject({
      kind: "decision",
      label: "Нужно твоё решение",
      happened: "Factory задала вопрос: Выбрать вариант A или B?",
    });
  });

  it("uses the pilot's paused and stuck statuses without guessing a retry", () => {
    const paused = build([task("paused", "Review", "failed", 1)], {}, [], {}, {
      "Экран Работа": { state: "stopped_owner", text: "остановлена: конвейер по этой работе на паузе" },
    })[0];
    const stuck = build([task("stuck", "Review", "failed", 1)], {}, [], {}, {
      "Экран Работа": { state: "stuck", text: "следующий этап не запускается" },
    })[0];

    expect(paused.status).toMatchObject({ kind: "paused", label: "Поставлено на паузу" });
    expect(stuck.status).toMatchObject({
      kind: "stuck", label: "Factory не может продолжить", happened: "следующий этап не запускается",
    });
  });

  it("archives cancelled and inactive old attempts while retaining successful completions", () => {
    const cancelled = build([task("cancelled", "Review", "cancelled", 1)], {}, [])[0];
    const closed = build([task("closed", "Review", "succeeded", 1)], {}, [], {
      "Экран Работа": { closed: "2026-08-08" },
    })[0];
    const inactiveRework = build([task("rework", "Review", "succeeded", 1)], {
      rework: { final_pass: false },
    }, [])[0];

    expect(cancelled.status.kind).toBe("archive");
    expect(closed.status.kind).toBe("done");
    expect(sectionOf(closed)).toBe("done");
    expect(inactiveRework.status).toMatchObject({
      kind: "archive", next: "Новый активный шаг в API не найден.",
    });
  });

  it("shows a successful standalone task in Done without a pipeline verdict", () => {
    const completed = {
      ...task("completed", "Implement + Test", "succeeded", 1),
      title: "Prove the complete local workflow",
    };
    const standalone = build([completed], {}, [])[0];
    const pipeline = build([task("verify", "Verify", "succeeded", 1)], {
      verify: { final_pass: true },
    }, [])[0];
    const failedLastAttempt = build([
      task("accepted", "Verify", "succeeded", 1),
      task("failed", "Implement + Test", "failed", 2),
    ], { accepted: { final_pass: true } }, [])[0];

    expect(standalone.status).toMatchObject({ kind: "done", label: "работа завершена" });
    expect(sectionOf(standalone)).toBe("done");
    expect(pipeline.status).toMatchObject({ kind: "done", label: "работа принята" });
    expect(sectionOf(failedLastAttempt)).toBe("archive");
  });

  it("waits for a post-merge delivery before completing Verify", () => {
    const waiting = build([task("verify", "Verify", "succeeded", 1)], {}, [])[0];

    expect(waiting.status).toMatchObject({
      kind: "active", label: "Ожидает слияния и выпуска",
    });
    expect(sectionOf(waiting)).not.toBe("done");
  });

  it("keeps a successful intermediate pipeline stage out of Done", () => {
    const triage = build([task("triage", "Triage", "succeeded", 1)], {}, [])[0];
    const specification = build([
      task("triage", "Triage", "succeeded", 1),
      task("specification", "Specification", "succeeded", 2),
    ], {}, [])[0];

    expect(triage.status).toMatchObject({
      kind: "queued",
      label: "Factory готовит следующий этап",
      next: "Следующий этап — «Спецификация». Factory запустит его, когда освободится исполнитель.",
    });
    expect(specification.status).toMatchObject({
      kind: "queued",
      label: "Factory готовит следующий этап",
      next: "Следующий этап — «Разработка». Factory запустит его, когда освободится исполнитель.",
    });
    expect(sectionOf(triage)).not.toBe("done");
    expect(sectionOf(specification)).not.toBe("done");
  });

  it("shows a prepared merge-conflict repair instead of the stale delivery wait", () => {
    const repairing = build([
      task("verify", "Verify", "succeeded", 1),
      task("implement-repair", "Implement + Test", "succeeded", 2),
    ], {}, [])[0];

    expect(repairing.status).toMatchObject({
      kind: "queued",
      label: "Factory готовит повторную проверку",
    });
    expect(repairing.status.label).not.toBe("Ожидает слияния и выпуска");
    expect(sectionOf(repairing)).not.toBe("done");
  });
});
