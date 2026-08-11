import { describe, expect, it } from "vitest";
import { build, sectionOf } from "./Work";
import type { Task } from "./types";

function task(id: string, stage: string, state: Task["state"], minute: number): Task {
  return {
    id,
    title: `[auto] [3/5 ${stage}] Экран Работа`,
    state,
    created_at: `2026-08-08T10:${String(minute).padStart(2, "0")}:00Z`,
  } as Task;
}

describe("build", () => {
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
});
