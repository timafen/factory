import { describe, expect, it } from "vitest";
import { cpuLoadExplanation } from "./Overview";

describe("cpuLoadExplanation", () => {
  it("uses actual running work and slot values", () => {
    expect(cpuLoadExplanation(3, { busy: 2, capacity: 4 }))
      .toBe("Причина загрузки процессора: активно работ 3; занято мест 2 из 4.");
  });

  it("does not invent occupied slots when the API omits them", () => {
    expect(cpuLoadExplanation(1))
      .toBe("Причина загрузки процессора: активно работ 1. Данных о занятых местах нет.");
  });

  it("reports zero running work without hiding slot data", () => {
    expect(cpuLoadExplanation(0, { busy: 0, capacity: 4 }))
      .toBe("Причина загрузки процессора: активно работ 0; занято мест 0 из 4.");
  });
});
