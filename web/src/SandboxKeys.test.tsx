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

  it("retries a temporary status error and reaches authorization", async () => {
    vi.useFakeTimers();
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })))
      .mockRejectedValueOnce(new Error("temporary network error"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", status: "authorized" })));
    render(<SandboxKeys />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));

    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    expect(screen.getByRole("alert")).toHaveTextContent("Повторяем проверку автоматически");
    await act(async () => vi.advanceTimersByTimeAsync(6_000));

    expect(screen.getByText("Ключи получены, продавец привязан.")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("keeps the verified start URL when status tries to replace it", async () => {
    vi.useFakeTimers();
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "javascript:alert(1)", access_token: "secret", status: "pending" })));
    render(<SandboxKeys />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));
    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    fireEvent.click(screen.getByRole("button", { name: "Открыть eBay" }));
    expect(open).toHaveBeenCalledWith("https://auth.example/consent", "_blank", "noopener,noreferrer");
  });

  it("ignores a status response for another operation", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-other", status: "authorized" })));
    render(<SandboxKeys />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));
    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    expect(screen.getByText(/Ожидаем согласия eBay/)).toBeVisible();
    expect(screen.queryByText("Ключи получены, продавец привязан.")).not.toBeInTheDocument();
  });

  it("polls sequentially and never regresses from an authorized state", async () => {
    vi.useFakeTimers();
    let finishAutomatic!: (response: Response) => void;
    const automatic = new Promise<Response>((resolve) => { finishAutomatic = resolve; });
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", consent_url: "https://auth.example/consent", status: "pending" })))
      .mockReturnValueOnce(automatic)
      .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "op-1", status: "authorized" })));
    render(<SandboxKeys />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Получить ключи продавца" })));
    await act(async () => vi.advanceTimersByTimeAsync(9_000));
    expect(fetch).toHaveBeenCalledTimes(2);

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Обновить" })));
    expect(screen.getByText("Ключи получены, продавец привязан.")).toBeVisible();
    await act(async () => finishAutomatic(new Response(JSON.stringify({ operation_id: "op-1", status: "pending" }))));
    expect(screen.getByText("Ключи получены, продавец привязан.")).toBeVisible();
    await act(async () => vi.advanceTimersByTimeAsync(6_000));
    expect(fetch).toHaveBeenCalledTimes(3);
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
