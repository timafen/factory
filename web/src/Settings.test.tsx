import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import type { PilotSettingsResponse } from "./types";

const response: PilotSettingsResponse = {
  version: "version-one",
  warnings: ["Unknown worker: worker-new"],
  settings: {
    _note: "owner note", enabled: true, poll_seconds: 10, timeout_seconds: 60, auto_merge: true, auto_answer: false,
    max_stage_attempts: 2, allow_any_worker: true, allowed_workers: ["worker-1"], max_parallel_subtasks: 2,
    day_cap_usd: 20, deploy_staging_cmd: "deploy", owner_chat_url: "https://example.test/chat", owner_ui_url: "https://example.test/ui",
    stages: [
      {workflow:"Triage",workers:{low:"worker-1",medium:"worker-1",high:"worker-new"}},
      {workflow:"Specification",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Implement + Test",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Review",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Verify",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
    ],
    skip_stages_for_low: ["Review"], stopped_pipelines: [], stage_base_usd: {"Triage":1,"Specification":1,"Implement + Test":2,"Review":1,"Verify":1},
    complexity_factor:{low:1,medium:2,high:3}, work_cap_usd:{low:2,medium:4,high:8}, ntfy_topic:"factory", ntfy_server:"https://ntfy.sh", ntfy_owner_topic:"owner",
    brain_chain:[{cli:"codex",model:"gpt",provider:"openai",note:"first"},{cli:"claude",model:"sonnet",provider:"anthropic",note:"second"}],
  },
};

function renderSettings(fetchImpl: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchImpl);
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  return render(<QueryClientProvider client={client}><Settings/></QueryClientProvider>);
}

it("shows all pilot sections, warnings, and saves an edited value without losing notes", async () => {
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...response,version:"version-two",settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  expect(await screen.findByRole("heading",{name:"Настройки"})).toBeVisible();
  expect(screen.getByText("Автоматизация и бюджеты")).toBeVisible(); expect(screen.getByText("Уведомления и ссылки владельца")).toBeVisible(); expect(screen.getByText("Цепочка моделей")).toBeVisible();
  expect(screen.getByText("Unknown worker: worker-new")).toBeVisible();
  const poll=screen.getByLabelText("Интервал проверки, секунд"); await user.clear(poll); await user.type(poll,"15"); await user.click(screen.getByRole("button",{name:"Сохранить настройки"}));
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT"); expect(put).toBeDefined();
  const body=JSON.parse(String(put![1]!.body)); expect(body.version).toBe("version-one"); expect(body.settings.poll_seconds).toBe(15); expect(body.settings._note).toBe("owner note"); expect(body.settings.brain_chain[0].note).toBe("first");
});

it("shows Russian field names and a visible explanation for every settings group", async () => {
  renderSettings(vi.fn(async()=>new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}})));
  expect(await screen.findByLabelText("Пилот включён")).toBeVisible();
  expect(screen.getByText("Разрешённые ID исполнителей")).toBeVisible();
  expect(screen.getByLabelText("Triage: низкая сложность")).toBeVisible();
  expect(screen.getByLabelText("Дневной лимит, USD")).toBeVisible();
  expect(screen.getByLabelText("Коэффициент сложности: средняя")).toBeVisible();
  expect(screen.getByLabelText("Сервер ntfy")).toBeVisible();
  expect(screen.getAllByLabelText("Команда CLI")).toHaveLength(2);
  expect(screen.getByLabelText("Заметка о конфигурации")).toBeVisible();
  for (const explanation of [
    "Как часто пилот проверяет очередь новых задач.",
    "Выберите исполнителя отдельно для каждой сложности этапа.",
    "Максимальные суммарные расходы пилота за день.",
    "Адрес сервера, через который Factory отправляет уведомления.",
    "Команда для запуска этого агента.",
    "Свободный комментарий для владельца: зачем и когда менялись настройки.",
  ]) expect(screen.getAllByText(explanation).length).toBeGreaterThan(0);
});

it("blocks strict routing to a worker outside the editable allow-list", async () => {
  const strict={...response,settings:{...response.settings,allow_any_worker:false}};
  renderSettings(vi.fn(async()=>new Response(JSON.stringify(strict),{status:200,headers:{"Content-Type":"application/json"}})));
  expect(await screen.findByText(/Every routed worker must be in the allowed list/)).toBeVisible();
  expect(screen.getByRole("button",{name:"Сохранить настройки"})).toBeDisabled();
});

it("allows adding a configuration note when the API omits it", async () => {
  const settingsWithoutNote={...response.settings}; delete settingsWithoutNote._note;
  const withoutNote={...response,settings:settingsWithoutNote};
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...withoutNote,settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(withoutNote),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  const note=await screen.findByLabelText("Заметка о конфигурации"); expect(note).toHaveValue("");
  await user.type(note,"new owner note"); await user.click(screen.getByRole("button",{name:"Сохранить настройки"}));
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings._note).toBe("new owner note");
});
