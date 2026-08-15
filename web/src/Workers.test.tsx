import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { WorkersView } from "./Workers";
import type { Worker } from "./types";

const now = new Date("2026-08-15T12:00:00.000Z").getTime();

function worker(id: string, name: string, heartbeat: number, online = false): Worker {
  return { id, name, last_heartbeat: Number.isNaN(heartbeat) ? "not-a-date" : new Date(heartbeat).toISOString(), online, health: "healthy", capacity: 2, active_count: 0, runtime: "codex", runtime_version: "1", worker_version: "1", repositories: [], retained_worktrees: [], registered_at: new Date(now).toISOString() };
}

function view(workers: Worker[]) {
  return render(<WorkersView workers={workers} pending={false} error={null} fetching={false} updatedAt={now} onRefresh={vi.fn()} onWorker={vi.fn()} />);
}

it("keeps online and recently offline workers current, archiving at exactly seven days", async () => {
  vi.spyOn(Date, "now").mockReturnValue(now);
  const user = userEvent.setup();
  view([
    worker("online", "Online worker", now - 30_000, true),
    worker("offline", "Offline worker", now - 30_001),
    worker("before", "Before boundary", now - 7 * 24 * 60 * 60 * 1000 + 1),
    worker("boundary", "At boundary", now - 7 * 24 * 60 * 60 * 1000),
    worker("invalid", "Invalid heartbeat", Number.NaN),
  ]);
  expect(screen.getByText("Current").nextElementSibling).toHaveTextContent("4");
  expect(screen.getByText("Online").nextElementSibling).toHaveTextContent("1");
  expect(screen.getByText("Available slots").nextElementSibling).toHaveTextContent("2");
  expect(screen.getByText("Archived").nextElementSibling).toHaveTextContent("1");
  expect(screen.getByText("Online worker").closest("button")).toHaveTextContent("Online");
  expect(screen.getByText("Offline worker").closest("button")).toHaveTextContent("Offline");
  expect(screen.queryByText("At boundary")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Archive (1)" }));
  expect(screen.getByText("At boundary")).toBeVisible();
});

it("returns an archived registration to the current fleet after a heartbeat", async () => {
  vi.spyOn(Date, "now").mockReturnValue(now);
  const archived = worker("same", "Returning worker", now - 7 * 24 * 60 * 60 * 1000);
  const { rerender } = view([archived]);
  expect(screen.getByText("No current workers")).toBeVisible();
  rerender(<WorkersView workers={[{ ...archived, last_heartbeat: new Date(now).toISOString(), online: true }]} pending={false} error={null} fetching={false} updatedAt={now} onRefresh={vi.fn()} onWorker={vi.fn()} />);
  expect(screen.getByText("Returning worker")).toBeVisible();
  expect(screen.queryByRole("button", { name: /Archive/ })).not.toBeInTheDocument();
});

it("distinguishes no registrations from an entirely archived fleet", () => {
  view([]);
  expect(screen.getByText("No workers registered")).toBeVisible();
});
