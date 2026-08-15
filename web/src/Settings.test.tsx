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
    max_stage_attempts: 2, allow_any_worker: true, allowed_workers: ["worker-1"], max_parallel_subtasks: 2, max_parallel_works: 4,
    day_cap_usd: 20, deploy_staging_cmd: "deploy staging", deploy_factory_cmd: "deploy factory", owner_chat_url: "https://example.test/chat", owner_ui_url: "https://example.test/ui",
    stages: [
      {workflow:"Triage",workers:{low:"worker-1",medium:"worker-1",high:"worker-new"}},
      {workflow:"Specification",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Implement + Test",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Review",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Verify",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
    ],
    skip_stages_for_low: ["Review"], stopped_pipelines: [], stage_base_usd: {"Triage":1,"Specification":1,"Implement + Test":2,"Review":1,"Verify":1},
    complexity_factor:{low:1,medium:2,high:3}, work_cap_usd:{low:2,medium:4,high:8}, ntfy_topic:"factory", ntfy_server:"https://ntfy.sh", ntfy_owner_topic:"owner",
    notify_groups:{questions:true,stuck:false,money:true,done:true,routine:false},
    project_providers:[{remote_identity:"github.com/acme/factory",type:"factory"}],
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
  expect(screen.getByRole("heading",{name:"Автоматизация и бюджеты"})).toBeVisible(); expect(screen.getByRole("heading",{name:"Уведомления и ссылки владельца"})).toBeVisible(); expect(screen.getByRole("heading",{name:"Цепочка моделей"})).toBeVisible();
  expect(screen.getByRole("navigation",{name:"Разделы настроек"}).querySelector('a[href="#settings-notifications"]')).toBeTruthy();
  expect(screen.getByText("Unknown worker: worker-new")).toBeVisible();
  const poll=screen.getByLabelText("Интервал проверки, секунд"); await user.clear(poll); await user.type(poll,"15"); const saves=screen.getAllByRole("button",{name:"Сохранить настройки"}); expect(saves).toHaveLength(2); await user.click(saves[0]);
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT"); expect(put).toBeDefined();
  const body=JSON.parse(String(put![1]!.body)); expect(body.version).toBe("version-one"); expect(body.settings.poll_seconds).toBe(15); expect(body.settings._note).toBe("owner note"); expect(body.settings.brain_chain[0].note).toBe("first"); expect(body.settings.deploy_factory_cmd).toBe("deploy factory");
});

it("edits and saves only a known product provider type", async () => {
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...response,settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  expect(await screen.findByText("Источники данных о продуктах")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("Тип источника"),"trade");
  await user.click(screen.getAllByRole("button",{name:"Сохранить настройки"})[0]);
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings.project_providers).toEqual([{remote_identity:"github.com/acme/factory",type:"trade"}]);
  expect(screen.queryByRole("textbox",{name:"Команда источника"})).not.toBeInTheDocument();
});

it("gives every settings field a Russian name and a non-empty explanation", async () => {
  const { container } = renderSettings(vi.fn(async()=>new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}})));
  await screen.findByRole("heading",{name:"Настройки"});
  const cyrillic=/[а-яё]/i;
  const labeledFields=container.querySelectorAll("label.field input[aria-label], label.field textarea[aria-label], label.settings-check input[aria-label]");
  expect(labeledFields.length).toBeGreaterThan(30);
  for (const field of labeledFields) {
    expect(field.getAttribute("aria-label")).toMatch(cyrillic);
    const hint=field.closest("label")?.querySelector(".field-hint");
    expect(hint, `no hint for "${field.getAttribute("aria-label")}"`).toBeTruthy();
    expect(hint!.textContent?.trim(), `empty hint for "${field.getAttribute("aria-label")}"`).toBeTruthy();
  }
  const stageSelects=container.querySelectorAll(".settings-stage-row select[aria-label]");
  expect(stageSelects.length).toBe(15);
  for (const select of stageSelects) expect(select.getAttribute("aria-label")).toMatch(cyrillic);
  expect(screen.getByText("Выберите исполнителя отдельно для каждой сложности этапа.")).toBeVisible();
  expect(screen.getByText("Выберите, о каких событиях присылать уведомления.")).toBeVisible();
});

it("shows every notification group in Russian with a hint and saves the changed selection", async () => {
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...response,settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  for(const label of ["Вопросы ко мне","Работа встала","Деньги и лимиты","Завершения и запуски задач","Рабочая рутина"]) expect(await screen.findByLabelText(label)).toBeVisible();
  expect(screen.getByText("Присылать уведомление, если задача остановилась и требует вмешательства.")).toBeVisible();
  expect(screen.getByLabelText("Работа встала")).not.toBeChecked();
  await user.click(screen.getByLabelText("Работа встала")); await user.click(screen.getAllByRole("button",{name:"Сохранить настройки"})[0]);
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings.notify_groups).toEqual({questions:true,stuck:true,money:true,done:true,routine:false,escalate:true});
});

it("uses pilot defaults when notification groups are absent", async () => {
  const settingsWithoutGroups={...response.settings}; delete settingsWithoutGroups.notify_groups;
  renderSettings(vi.fn(async()=>new Response(JSON.stringify({...response,settings:settingsWithoutGroups}),{status:200,headers:{"Content-Type":"application/json"}})));
  for(const label of ["Вопросы ко мне","Работа встала","Деньги и лимиты","Завершения и запуски задач"]) expect(await screen.findByLabelText(label)).toBeChecked();
  expect(screen.getByLabelText("Рабочая рутина")).not.toBeChecked();
});

it("blocks strict routing to a worker outside the editable allow-list", async () => {
  const strict={...response,settings:{...response.settings,allow_any_worker:false}};
  renderSettings(vi.fn(async()=>new Response(JSON.stringify(strict),{status:200,headers:{"Content-Type":"application/json"}})));
  expect(await screen.findByText(/Каждый назначенный исполнитель должен быть в разрешённом списке/)).toBeVisible();
  for (const save of screen.getAllByRole("button",{name:"Сохранить настройки"})) expect(save).toBeDisabled();
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
  await user.type(note,"new owner note"); await user.click(screen.getAllByRole("button",{name:"Сохранить настройки"})[0]);
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings._note).toBe("new owner note");
});

it("changes the brain-chain order and saves notes with that order", async () => {
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...response,settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  const moveUp=await screen.findAllByRole("button",{name:"Поднять"});
  await user.click(moveUp[1]);
  await user.click(screen.getAllByRole("button",{name:"Сохранить настройки"})[0]);
  await screen.findByText(/Настройки сохранены/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings.brain_chain).toEqual([
    {cli:"claude",model:"sonnet",provider:"anthropic",note:"second"},
    {cli:"codex",model:"gpt",provider:"openai",note:"first"},
  ]);
});

it("offers to reload current settings after a version conflict", async () => {
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({error:{code:"config_conflict",message:"Настройки уже изменились. Загрузите свежую версию."}}),{status:409,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(response),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  await screen.findByRole("heading",{name:"Настройки"});
  await user.click(screen.getAllByRole("button",{name:"Сохранить настройки"})[0]);
  expect(await screen.findByText("Настройки уже изменились. Загрузите свежую версию.")).toBeVisible();
  await user.click(screen.getByRole("button",{name:"Загрузить свежие настройки"}));
  expect(fetchMock.mock.calls.filter(([,init])=>!init?.method)).toHaveLength(2);
});
