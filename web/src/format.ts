import type { AttemptEvent, TaskState } from "./types";

export const taskStates: TaskState[] = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

export function stateLabel(state: string): string {
  return state.charAt(0).toUpperCase() + state.slice(1);
}

export function runtimeLabel(runtime: string): string {
  return runtime === "claude-code" ? "Claude Code" : "Codex";
}

export function timeAgo(value: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.floor((now - new Date(value).getTime()) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function duration(start: string, end?: string, now = Date.now()): string {
  const elapsed = Math.max(0, (end ? new Date(end).getTime() : now) - new Date(start).getTime());
  const seconds = Math.floor(elapsed / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export interface EventSummary {
  label: string;
  text: string;
}

const hiddenEventTypes = new Set([
  "rate_limit_event",
  "reasoning",
  "system",
  "thread.started",
  "turn.started",
  "turn.completed",
]);

export function eventSummary(event: AttemptEvent): EventSummary | null {
  if (event.kind === "stdout" || event.kind === "stderr") return null;
  if (typeof event.payload === "string") {
    return { label: eventLabel(event.kind), text: event.payload };
  }
  const payload = record(event.payload);
  if (!payload) return null;

  const type = stringValue(payload.type);
  if (type === "assistant") return claudeAssistantSummary(payload);
  if (type === "user") return claudeToolResultSummary(payload);
  if (type === "result") {
    const result = stringValue(payload.result);
    if (payload.is_error === true) {
      return { label: "Ошибка", text: result ?? "Исполнитель сообщил об ошибке" };
    }
    return result ? { label: "Результат", text: result } : null;
  }
  if (type === "item.started" || type === "item.completed") {
    return codexItemSummary(payload, type === "item.completed");
  }
  if (type === "error") {
    return { label: "Ошибка", text: errorText(payload) ?? "Исполнитель сообщил об ошибке" };
  }
  if (type === "turn.failed") {
    return { label: "Ошибка", text: errorText(payload) ?? "Исполнитель не смог завершить работу" };
  }
  if (type && hiddenEventTypes.has(type)) return null;

  const stream = stringValue(payload.stream);
  if (stream === "stdout" || stream === "stderr") return null;
  if (type) return null;
  const directText = firstString(payload, ["text", "message", "title", "summary"]);
  if (directText) {
    return { label: eventLabel(event.kind), text: directText };
  }
  return null;
}

function claudeAssistantSummary(payload: Record<string, unknown>): EventSummary | null {
  const message = record(payload.message);
  if (!message || !Array.isArray(message.content)) return null;
  const lines: string[] = [];
  for (const value of message.content) {
    const block = record(value);
    if (!block) continue;
    if (block.type === "text") {
      const text = stringValue(block.text);
      if (text) lines.push(text);
      continue;
    }
    if (block.type === "tool_use") {
      lines.push(toolAction(block, false));
    }
  }
  return lines.length > 0 ? { label: "Исполнитель", text: lines.join("\n\n") } : null;
}

function claudeToolResultSummary(payload: Record<string, unknown>): EventSummary | null {
  const message = record(payload.message);
  if (!message || !Array.isArray(message.content)) return null;
  const blocks = message.content.map(record).filter((value) => value?.type === "tool_result");
  if (blocks.length === 0) return null;
  const failed = blocks.some((block) => block?.is_error === true);
  return {
    label: failed ? "Ошибка инструмента" : "Инструмент",
    text: failed ? "Инструмент завершился с ошибкой" : "Инструмент завершил работу",
  };
}

function codexItemSummary(payload: Record<string, unknown>, completed: boolean): EventSummary | null {
  const item = record(payload.item);
  if (!item) return null;
  const type = stringValue(item.type);
  const failed = completed && (item.status === "failed" || (item.error !== undefined && item.error !== null));
  if (type === "agent_message") {
    const text = stringValue(item.text);
    return text ? { label: "Исполнитель", text } : null;
  }
  if (type === "reasoning") return null;
  if (type === "command_execution") {
    const command = compactLine(stringValue(item.command) ?? "команда без названия");
    if (!completed) return { label: "Команда", text: `Запускаю: ${command}` };
    const exitCode = numberValue(item.exit_code);
    if (!failed && exitCode === 0) return { label: "Команда", text: `Выполнено: ${command}` };
    if (exitCode !== null) {
      return { label: "Ошибка команды", text: `Код ${exitCode}: ${command}` };
    }
    if (failed) return { label: "Ошибка команды", text: `Не удалось выполнить: ${command}` };
    return { label: "Команда", text: `Завершено: ${command}` };
  }
  if (type?.includes("tool_call")) {
    return {
      label: failed ? "Ошибка инструмента" : "Инструмент",
      text: toolAction(item, completed, failed),
    };
  }
  if (type === "file_change") {
    return {
      label: failed ? "Ошибка файлов" : "Файлы",
      text: failed ? "Не удалось изменить файлы" : completed ? "Файлы изменены" : "Изменяю файлы",
    };
  }
  return null;
}

function toolAction(value: Record<string, unknown>, completed: boolean, failed = false): string {
  const name = firstString(value, ["tool", "name"]) ?? "без названия";
  if (failed) return `Инструмент завершился с ошибкой: ${name}`;
  return completed ? `Инструмент завершил работу: ${name}` : `Запущен инструмент: ${name}`;
}

function eventLabel(kind: string): string {
  if (kind === "claude-code" || kind === "codex") return "Исполнитель";
  if (kind === "progress") return "Ход работы";
  if (kind === "check") return "Проверка";
  return stateLabel(kind);
}

function errorText(payload: Record<string, unknown>): string | null {
  const direct = firstString(payload, ["error", "message"]);
  if (direct) return direct;
  const error = record(payload.error);
  return error ? firstString(error, ["message", "detail"]) : null;
}

function compactLine(value: string): string {
  const line = value.replace(/\s+/g, " ").trim();
  const maximum = 240;
  return line.length > maximum ? `${line.slice(0, maximum)}…` : line;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function firstString(value: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const found = stringValue(value[key]);
    if (found) return found;
  }
  return null;
}
