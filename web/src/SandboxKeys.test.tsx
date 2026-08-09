import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SandboxKeys } from "./SandboxKeys";

describe("SandboxKeys", () => {
  afterEach(() => vi.useRealTimers());
  it("starts seller consent and opens eBay only after the owner's click", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })));
    render(<SandboxKeys />);
    fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" }));
    const openButton = await screen.findByRole("button", { name: "Открыть eBay" });
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(openButton);
    expect(open).toHaveBeenCalledWith("https://auth.example/consent", "_blank", "noopener,noreferrer");
  });

  it("polls the safe status until authorization", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", status: "authorized" })));
    render(<SandboxKeys />);
    fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" }));
    await screen.findByRole("status");
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(screen.getByText("Ключи получены, продавец привязан.")).toBeVisible());
  });
});
