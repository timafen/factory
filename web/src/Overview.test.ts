import { describe, expect, it } from "vitest";
import { cpuLoadExplanation } from "./Overview";

describe("cpuLoadExplanation", () => {
  it("explains CPU load through active work and occupied slots", () => {
    expect(cpuLoadExplanation(3, { busy: 4, capacity: 6 })).toBe(
      "Сейчас активно работ: 3; занято 4 из 6 мест. Данных о нагрузке отдельных процессов нет.",
    );
  });

  it("does not invent slot attribution when slot data is absent", () => {
    expect(cpuLoadExplanation(2)).toContain("число занятых мест неизвестно");
  });
});
