import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SandboxKeys } from "./SandboxKeys";

describe("SandboxKeys", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });
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
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));
    expect(screen.getByRole("status")).toBeVisible();
    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    expect(screen.getByText("Ключи получены, продавец привязан.")).toBeVisible();
  });

  it("explains a failed consent and lets the owner start again", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", status: "failed", message: "eBay отклонил согласие." })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-2", consent_url: "https://auth.example/retry", status: "pending" })));
    render(<SandboxKeys />);

    fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("eBay отклонил согласие.");
    fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" }));

    expect(await screen.findByRole("button", { name: "Открыть eBay" })).toBeVisible();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it("stops polling after the owner leaves the screen", async () => {
    vi.useFakeTimers();
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })));
    const view = render(<SandboxKeys />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));
    expect(screen.getByRole("status")).toBeVisible();

    view.unmount();
    await act(async () => vi.advanceTimersByTimeAsync(6_000));

    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
