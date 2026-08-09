import { describe, expect, it } from "vitest";
import { eventSummary } from "./format";
import type { AttemptEvent } from "./types";

function event(payload: unknown, kind = "codex"): AttemptEvent {
  return { sequence: 0, kind, payload, server_time: "2026-07-31T12:00:00Z" };
}

describe("eventSummary", () => {
  it("renders Codex assistant messages without their event envelope", () => {
    expect(eventSummary(event({
      type: "item.completed",
      item: { id: "item-1", type: "agent_message", text: "The tests pass." },
    }))).toEqual({ label: "Исполнитель", text: "The tests pass." });
  });

  it("summarizes successful and failed Codex commands without captured output", () => {
    const successful = eventSummary(event({
      type: "item.completed",
      item: {
        type: "command_execution",
        command: "go test ./...",
        aggregated_output: "large and unreadable output",
        exit_code: 0,
      },
    }));

    expect(successful).toEqual({ label: "Команда", text: "Выполнено: go test ./..." });
    expect(successful?.text).not.toContain("unreadable output");
    expect(eventSummary(event({
      type: "item.completed",
      item: {
        type: "command_execution",
        command: "npm run typecheck",
        aggregated_output: "secret compiler output",
        exit_code: 2,
      },
    }))).toEqual({ label: "Ошибка команды", text: "Код 2: npm run typecheck" });
  });

  it("describes Codex tools and file changes without internal payloads", () => {
    expect(eventSummary(event({
      type: "item.started",
      item: { type: "mcp_tool_call", tool: "js", input: { token: "private-token" } },
    }))).toEqual({ label: "Инструмент", text: "Запущен инструмент: js" });
    const tool = eventSummary(event({
      type: "item.completed",
      item: {
        id: "internal-call-id",
        type: "mcp_tool_call",
        tool: "js",
        input: { command: "private tool input" },
        result: "private tool result",
      },
    }));
    expect(tool).toEqual({ label: "Инструмент", text: "Инструмент завершил работу: js" });
    expect(tool?.text).not.toMatch(/internal-call-id|private tool input|private tool result/);
    expect(eventSummary(event({
      type: "item.completed",
      item: { type: "mcp_tool_call", tool: "js", status: "failed", error: "private detail" },
    }))).toEqual({
      label: "Ошибка инструмента",
      text: "Инструмент завершился с ошибкой: js",
    });
    expect(eventSummary(event({
      type: "item.started",
      item: { type: "file_change", changes: [{ path: "/private/path" }] },
    }))).toEqual({ label: "Файлы", text: "Изменяю файлы" });
    expect(eventSummary(event({
      type: "item.completed",
      item: { type: "file_change", changes: [{ path: "/private/path" }] },
    }))).toEqual({ label: "Файлы", text: "Файлы изменены" });
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
      label: "Исполнитель",
      text: "I found the failure.\n\nЗапущен инструмент: Bash",
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

    expect(summary).toEqual({ label: "Инструмент", text: "Инструмент завершил работу" });
    expect(summary?.text).not.toContain("private command output");
    expect(eventSummary(event({
      type: "user",
      message: {
        content: [{ type: "tool_result", content: "private failure", is_error: true }],
      },
    }, "claude-code"))).toEqual({
      label: "Ошибка инструмента",
      text: "Инструмент завершился с ошибкой",
    });
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
      text: "Исполнитель сообщил об ошибке",
    });
  });

  it("preserves nested errors from failed Codex turns", () => {
    expect(eventSummary(event({
      type: "turn.failed",
      error: { message: "The model provider rejected the request." },
    }))).toEqual({ label: "Ошибка", text: "The model provider rejected the request." });
  });

  it("hides lifecycle, telemetry, and reasoning events", () => {
    expect(eventSummary(event({ type: "thread.started", thread_id: "thread-1" }))).toBeNull();
    expect(eventSummary(event({ type: "system", subtype: "thinking_tokens" }, "claude-code"))).toBeNull();
    expect(eventSummary(event({
      type: "item.completed",
      item: { type: "reasoning", text: "private chain of thought" },
    }))).toBeNull();
  });

  it("hides raw stdout and stderr events", () => {
    expect(eventSummary(event({
      stream: "stdout",
      text: "large command output",
    }))).toBeNull();
    expect(eventSummary(event({ stream: "stderr", text: "secret failure detail" }))).toBeNull();
    expect(eventSummary(event("raw output", "stdout"))).toBeNull();
  });

  it("hides unknown object events instead of inventing a runtime update", () => {
    expect(eventSummary(event({ unfamiliar: { deeply: "nested" } }))).toBeNull();
    expect(eventSummary(event({ type: "telemetry.pulse", session_id: "private-id" }))).toBeNull();
    expect(eventSummary(event({
      type: "unknown.event",
      message: "unknown payload must stay hidden",
    }))).toBeNull();
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

  it("keeps the order of the remaining Codex and Claude events", () => {
    const summaries = [
      event({ type: "thread.started", thread_id: "hidden" }),
      event({ type: "item.completed", item: { type: "agent_message", text: "Первое сообщение" } }),
      event({ stream: "stdout", text: "hidden output" }),
      event({
        type: "assistant",
        message: { content: [{ type: "text", text: "Второе сообщение" }] },
      }, "claude-code"),
    ].map(eventSummary).filter((summary) => summary !== null);

    expect(summaries.map((summary) => summary.text)).toEqual([
      "Первое сообщение",
      "Второе сообщение",
    ]);
  });
});
