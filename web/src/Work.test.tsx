import { describe, expect, it } from "vitest";
import type { Task } from "./types";
import { buildWorkGroups } from "./Work";

const task = (id: string, stage: string, state: Task["state"], minute: number): Task => ({
  id,
  request_key: id,
  title: `[auto] [${minute + 1}/5 ${stage}] Исправить экран`,
  worker_id: "worker-1",
  repository_id: "repo-1",
  timeout_seconds: 3600,
  state,
  created_at: `2026-08-08T10:0${minute}:00Z`,
});

describe("buildWorkGroups", () => {
  it("marks the repeated live stage as again, not later stages", () => {
    const tasks = [
      task("implement-1", "Implement + Test", "succeeded", 0),
      task("review-1", "Review", "succeeded", 1),
      task("implement-2", "Implement + Test", "running", 2),
    ];
    const [work] = buildWorkGroups(tasks, {}, []);
    expect(work.currentStage).toBe("Implement + Test");
    expect(work.reached["Implement + Test"]).toBe("again");
    expect(work.reached.Review).toBe("done");
    expect(work.reached.Verify).not.toBe("again");
  });

  it("recognizes a repeated stage after a new lap started earlier", () => {
    const stages = ["Triage", "Specification", "Implement + Test", "Review", "Triage", "Specification"];
    const tasks = stages.map((stage, index) => task(`task-${index}`, stage, "succeeded", index));
    tasks.push(task("implement-live", "Implement + Test", "running", stages.length));
    const [work] = buildWorkGroups(tasks, {}, []);
    expect(work.reached["Implement + Test"]).toBe("again");
    expect(work.reached.Review).toBe("done");
  });
});
