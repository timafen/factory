import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ProjectsView } from "./Projects";

function renderProjects(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><ProjectsView /></QueryClientProvider>);
}

it("creates only a named v1 staging template without command or executor input", async () => {
  const requests: Array<{ path: string; init?: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input); requests.push({ path, init });
    if (init?.method === "POST") {
      const submitted = JSON.parse(String(init.body));
      return new Response(JSON.stringify({ ...submitted, id: "project-1", repository_id: "repo-1", executor_group: "automation-ebay-staging", created_at: new Date().toISOString(), updated_at: new Date().toISOString() }), { status: 201, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ projects: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  renderProjects(fetchMock); const user = userEvent.setup();
  expect(await screen.findByRole("heading", { name: "Безопасные проекты" })).toBeVisible();
  expect(screen.queryByLabelText(/команда/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/группа/i)).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Название проекта"), "Tarser staging");
  await user.selectOptions(screen.getByLabelText("Тип проекта"), "tarser-operations-staging");
  await user.click(screen.getByRole("button", { name: "Подключить проект" }));
  await screen.findByRole("heading", { name: "Tarser staging" });
  const post = requests.find((request) => request.init?.method === "POST");
  const body = JSON.parse(String(post?.init?.body));
  expect(body).toMatchObject({ remote_identity: "github.com/timafen/tarser-operations", project_type: "tarser-operations-staging", required_checks: ["secret-scan", "static-typecheck", "tests", "build"] });
  expect(body.environments[0]).toMatchObject({ blocked: false, release_adapter: "tarser-staging-deploy-release", rollback_adapter: "tarser-staging-auto-rollback", web_hosts: ["staging-automation.tarser.net"] });
  expect(body).not.toHaveProperty("executor_group"); expect(body).not.toHaveProperty("command");
});

it("shows fail-closed gates and secret presence without any secret value", async () => {
  const project = { id: "project-1", repository_id: "repo-1", name: "Factory", remote_identity: "github.com/timafen/factory", main_branch: "main", project_type: "factory-single-instance", executor_group: "factory", required_checks: ["secret-scan", "static-typecheck", "tests", "build"], environments: [{ name: "staging", url: "https://factory.timafen.com", health_url: "https://factory.timafen.com/api/v1/dashboard", blocked: false, release_adapter: "fx-factory-release", rollback_adapter: "fx-factory-rollback", required_secrets: ["GITHUB_TOKEN"], web_hosts: ["factory.timafen.com"] }], created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => String(input).includes("readiness")
    ? new Response(JSON.stringify({ ready: false, gates: [{ name: "build", ready: false, reason: "missing" }], secrets: [{ name: "GITHUB_TOKEN", present: false }], routing_reason: "missing" }), { status: 200, headers: { "Content-Type": "application/json" } })
    : new Response(JSON.stringify({ projects: [project] }), { status: 200, headers: { "Content-Type": "application/json" } }));
  renderProjects(fetchMock);
  expect(await screen.findByText("GITHUB_TOKEN: нет")).toBeVisible();
  expect(screen.getByText("Закрыт")).toBeVisible();
  expect(screen.queryByText("super-secret-value")).not.toBeInTheDocument();
});
