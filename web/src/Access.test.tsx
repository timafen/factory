import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AccessView } from "./Access";

const scope = {
  key: "ssh", title: "SSH на сервер", description: "Доступ по SSH.",
  enabled: false, ui_toggleable: true,
};

function renderAccess(fetchImpl: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchImpl);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><AccessView /></QueryClientProvider>);
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

it("shows the scope loaded from GET /api/v1/access with its current state", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/access")) return jsonResponse({ scopes: [scope] });
    if (url.includes("/api/v1/limits")) return jsonResponse({ limits: {} });
    throw new Error(`unexpected fetch: ${url}`);
  });
  renderAccess(fetchMock);
  expect(await screen.findByText("SSH на сервер")).toBeVisible();
  expect(screen.getByText("закрыт")).toBeVisible();
});

it("re-fetches the access list after toggling a scope", async () => {
  let enabled = false;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/v1/limits")) return jsonResponse({ limits: {} });
    if (url.match(/\/api\/v1\/access\/ssh$/) && init?.method === "POST") {
      enabled = true;
      return jsonResponse({ ok: true });
    }
    if (url.endsWith("/api/v1/access")) return jsonResponse({ scopes: [{ ...scope, enabled }] });
    throw new Error(`unexpected fetch: ${url}`);
  });
  renderAccess(fetchMock);
  const user = userEvent.setup();
  await screen.findByText("закрыт");
  await user.click(screen.getByRole("button", { name: "Открыть" }));
  await screen.findByText("открыт");
  const getCalls = fetchMock.mock.calls.filter(([req]) => String(req).endsWith("/api/v1/access"));
  expect(getCalls.length).toBeGreaterThanOrEqual(2);
});
