import type { AutomationOccurrence } from "./types";

export function occurrenceFinding(result: string | undefined): string[] {
  return (result ?? "").split(/\r?\n/)
    .filter((line) => line.startsWith("НАХОДКА:"))
    .map((line) => line.slice("НАХОДКА:".length).trim())
    .filter(Boolean);
}

export function occurrenceOutcome(occurrence: AutomationOccurrence): string {
  const outcome = occurrence.result?.trim() || occurrence.error?.trim();
  return outcome || "Результат не оставлен";
}
