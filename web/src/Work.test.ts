import { describe, expect, it } from "vitest";
import { build } from "./Work";
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
});
