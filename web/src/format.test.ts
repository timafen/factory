import { describe, expect, it } from "vitest";
import { eventSummary, stateLabel, timeAgo } from "./format";
import type { AttemptEvent } from "./types";

function event(payload: unknown, kind = "codex"): AttemptEvent {
  return { sequence: 0, kind, payload, server_time: "2026-07-31T12:00:00Z" };
}

describe("eventSummary", () => {
  it("renders Codex assistant messages without their event envelope", () => {
    expect(eventSummary(event({
      type: "item.completed",
      item: { id: "item-1", type: "agent_message", text: "The tests pass." },
    }))).toEqual({ label: "Агент", text: "The tests pass." });
  });

  it("summarizes Codex commands without exposing captured output", () => {
    const summary = eventSummary(event({
      type: "item.completed",
      item: {
        type: "command_execution",
        command: "go test ./...",
        aggregated_output: "large and unreadable output",
        exit_code: 0,
      },
    }));

    expect(summary).toEqual({ label: "Команда", text: "Успешно: go test ./..." });
    expect(summary?.text).not.toContain("unreadable output");
  });

  it("reports failed Codex tool calls and file changes as errors", () => {
    expect(eventSummary(event({
      type: "item.completed",
      item: { type: "mcp_tool_call", tool: "js", status: "failed", error: "private detail" },
    }))).toEqual({ label: "Ошибка инструмента", text: "js: ошибка" });
    expect(eventSummary(event({
      type: "item.completed",
      item: { type: "file_change", status: "failed" },
    }))).toEqual({ label: "Ошибка файлов", text: "Не удалось изменить файлы" });
  });

  it("renders Claude text and tool use from a nested assistant message", () => {
    expect(eventSummary(event({
      type: "assistant",
      session_id: "secret-session",
      message: {
        model: "claude-test",
        content: [
          { type: "text", text: "I found the failure." },
          { type: "tool_use", name: "Bash", input: { command: "go test ./internal/controlplane" } },
        ],
      },
    }, "claude-code"))).toEqual({
      label: "Агент",
      text: "I found the failure.\n\nИспользует Bash: go test ./internal/controlplane",
    });
  });

  it("summarizes Claude tool results without showing their contents", () => {
    const summary = eventSummary(event({
      type: "user",
      tool_use_result: { stdout: "private command output" },
      message: {
        content: [{ type: "tool_result", content: "private command output", is_error: false }],
      },
    }, "claude-code"));

    expect(summary).toEqual({ label: "Инструмент", text: "Вызов инструмента завершён" });
    expect(summary?.text).not.toContain("private command output");
  });

  it("reports failed Claude terminal results as errors", () => {
    expect(eventSummary(event({
      type: "result",
      is_error: true,
      result: "The release check failed.",
    }, "claude-code"))).toEqual({ label: "Ошибка", text: "The release check failed." });
    expect(eventSummary(event({
      type: "result",
      is_error: true,
      result: "",
    }, "claude-code"))).toEqual({
      label: "Ошибка",
      text: "Claude Code сообщил о финальной ошибке",
    });
  });

  it("preserves nested errors from failed Codex turns", () => {
    expect(eventSummary(event({
      type: "turn.failed",
      error: { message: "The model provider rejected the request." },
    }))).toEqual({ label: "Ошибка", text: "The model provider rejected the request." });
  });

  it("hides lifecycle and telemetry events", () => {
    expect(eventSummary(event({ type: "thread.started", thread_id: "thread-1" }))).toBeNull();
    expect(eventSummary(event({ type: "system", subtype: "thinking_tokens" }, "claude-code"))).toBeNull();
  });

  it("omits large truncated structured output", () => {
    expect(eventSummary(event({
      stream: "stdout",
      text: '{"large":"runtime envelope',
      truncated: true,
    }))).toEqual({ label: "Вывод", text: "Крупный структурированный вывод среды выполнения скрыт" });
  });

  it("never serializes an unknown object as raw JSON", () => {
    const summary = eventSummary(event({ unfamiliar: { deeply: "nested" } }));

    expect(summary).toEqual({ label: "Среда выполнения", text: "Обновление среды выполнения" });
    expect(summary?.text).not.toContain("unfamiliar");
  });

  it("preserves existing string and top-level message events", () => {
    expect(eventSummary(event("Plain progress", "progress"))).toEqual({
      label: "Ход работы",
      text: "Plain progress",
    });
    expect(eventSummary(event({ message: "Task completed" }, "progress"))).toEqual({
      label: "Ход работы",
      text: "Task completed",
    });
  });

  it("uses one Russian dictionary for task states and fresh timestamps", () => {
    expect(stateLabel("queued")).toBe("В очереди");
    expect(stateLabel("running")).toBe("В работе");
    expect(stateLabel("succeeded")).toBe("Успешно");
    expect(stateLabel("failed")).toBe("Ошибка");
    expect(stateLabel("cancelled")).toBe("Отменено");
    expect(timeAgo(new Date(1_000).toISOString(), 5_000)).toBe("только что");
  });
});
