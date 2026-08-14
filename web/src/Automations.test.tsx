import { describe, expect, it } from "vitest";
import { occurrenceFinding, occurrenceOutcome } from "./Automations";

describe("automation run findings", () => {
  it("extracts only canonical finding lines and keeps the full result as outcome", () => {
    const result = "НАХОДКА: просрочен сертификат\r\nИтоговая проверка завершена\nНАХОДКА: нет владельца";
    expect(occurrenceFinding(result)).toEqual(["просрочен сертификат", "нет владельца"]);
    expect(occurrenceOutcome({ result } as never)).toBe(result);
  });

  it("uses saved error and stays neutral when no attempt output exists", () => {
    expect(occurrenceOutcome({ error: "worker недоступен" } as never)).toBe("worker недоступен");
    expect(occurrenceFinding(undefined)).toEqual([]);
    expect(occurrenceOutcome({} as never)).toBe("Результат не оставлен");
  });
});
