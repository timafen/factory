import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ProjectOnboardingPanel } from "./ProjectOnboarding";

function renderPanel(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ProjectOnboardingPanel repositoryID="repo-1" remoteIdentity="github.com/timafen/tarser-operations" repositoryEnabled={false} /></QueryClientProvider>);
}

it("saves and reloads an inert disabled project card without execution controls", async () => {
  const requests: Array<{ path: string; init?: RequestInit }> = [];
  let card: Record<string, unknown> | null = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input); requests.push({ path, init });
    if (!init?.method && !card) return new Response(JSON.stringify({ error: { code: "not_found", message: "resource not found" } }), { status: 404, headers: { "Content-Type": "application/json" } });
    if (init?.method === "PUT") {
      const submitted = JSON.parse(String(init.body));
      card = { ...submitted, repository_id: "repo-1", remote_identity: "github.com/timafen/tarser-operations", enabled: false };
    }
    return new Response(JSON.stringify(card), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  renderPanel(fetchMock);
  const user = userEvent.setup();
  expect(await screen.findByDisplayValue("Tarser")).toBeVisible();
  expect(screen.getByText(/Network NONE · secrets NONE · write NONE/)).toBeVisible();
  expect(screen.queryByRole("button", { name: /doctor|trial/i })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Save disabled card" }));
  expect(await screen.findByText("Disabled card saved")).toBeVisible();
  const put = requests.find((request) => request.init?.method === "PUT");
  const body = JSON.parse(String(put?.init?.body));
  expect(body).toMatchObject({
    project_id: "tarser", default_branch: "main", timeout_seconds: 120,
    environment: { network: "NONE", secrets: "NONE" },
    policy: { write: "NONE", pull_request: "DISABLED", release: "DISABLED" },
    commands: { test: { argv: ["git", "diff", "--check"] } },
  });
  expect(screen.getByText(/Card enabled: no/)).toHaveTextContent("readiness: unset");
  expect(requests.some((request) => request.path.endsWith("/doctor") || request.path.endsWith("/trial"))).toBe(false);
});

it("blocks onboarding actions while repository routing is enabled", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "not_found", message: "resource not found" } }), { status: 404, headers: { "Content-Type": "application/json" } })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProjectOnboardingPanel repositoryID="repo-1" remoteIdentity="github.com/timafen/assistant" repositoryEnabled /></QueryClientProvider>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Disable repository routing");
  expect(screen.getByRole("button", { name: "Save disabled card" })).toBeDisabled();
});
