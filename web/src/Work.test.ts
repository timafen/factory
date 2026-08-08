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
});
