import { describe, expect, it } from "vitest";
import { whatChanged } from "./whatChanged";

describe("whatChanged", () => {
  it("shows the human part of the Verify report and hides delivery fields", () => {
    const report = [
      "PASS",
      "Добавлен понятный блок с результатом принятой работы.",
      "BRANCH: factory/example",
      "HEAD: 0123abc",
      "PUSHED: yes",
      "TRY: /tasks/example",
    ].join("\n");

    expect(whatChanged(report, "Запасной отчёт попытки")).toBe(
      "Добавлен понятный блок с результатом принятой работы.",
    );
  });

  it("uses the latest attempt result when Verify left no verdict", () => {
    expect(whatChanged("", "Исправлено отображение результата для владельца.")).toBe(
      "Исправлено отображение результата для владельца.",
    );
  });

  it("uses the attempt result when the Verify report contains only internal lines", () => {
    expect(
      whatChanged(
        "PASS\nHEAD: 0123abc\nPUSHED: yes",
        "Исправлено отображение результата для владельца.",
      ),
    ).toBe("Исправлено отображение результата для владельца.");
  });

  it("never leaves the block empty when only internal lines are available", () => {
    expect(whatChanged("PASS\nHEAD: 0123abc\nPUSHED: yes")).toBe(
      "Проверка прошла, подробностей исполнитель не оставил.",
    );
  });

  it("keeps unfamiliar lines visible", () => {
    expect(whatChanged("Status: ready\nНеизвестная строка отчёта")).toBe(
      "Status: ready\nНеизвестная строка отчёта",
    );
  });
});
