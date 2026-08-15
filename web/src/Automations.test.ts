import { describe, expect, it } from "vitest";
import { automationHealthMessage } from "./Automations";

describe("automationHealthMessage", () => {
  it("uses stable codes and never exposes an unknown server message", () => {
    expect(automationHealthMessage("workflow_disabled", "Workflow is disabled.")).toBe("Сценарий выключен.");
    expect(automationHealthMessage("gh_unauthenticated", "gh is not authenticated.")).toBe("GitHub CLI не авторизован для github.com.");
    expect(automationHealthMessage("future_code", "An English server diagnostic.")).toBe("Состояние автоматизации требует внимания.");
  });
});
