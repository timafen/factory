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
    max_stage_attempts: 2, max_work_rounds: 3, max_cap_rescues: 4, notify_groups: {owner:true,progress:false}, allow_any_worker: true, allowed_workers: ["worker-1"], max_parallel_subtasks: 2,
    day_cap_usd: 20, deploy_staging_cmd: "deploy", owner_chat_url: "https://example.test/chat", owner_ui_url: "https://example.test/ui",
    stages: [
      {workflow:"Triage",workers:{low:"worker-1",medium:"worker-1",high:"worker-new"}}, {workflow:"Specification",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
      {workflow:"Implement + Test",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}}, {workflow:"Review",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}}, {workflow:"Verify",workers:{low:"worker-1",medium:"worker-1",high:"worker-1"}},
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
  expect(await screen.findByRole("heading",{name:"Pilot settings"})).toBeVisible();
  expect(screen.getByText("Automation and budgets")).toBeVisible(); expect(screen.getByText("Notifications and owner links")).toBeVisible(); expect(screen.getByText("Brain chain")).toBeVisible();
  expect(screen.getByLabelText("Maximum work rounds")).toHaveValue(3);
  expect(screen.getByLabelText("Maximum cap rescues")).toHaveValue(4);
  expect(screen.getByText("Notification groups (notify_groups)")).toBeVisible();
  expect(screen.getByLabelText("Notify group: owner")).toBeChecked();
  expect(screen.getByLabelText("Notify group: progress")).not.toBeChecked();
  expect(screen.getByText("Unknown worker: worker-new")).toBeVisible();
  const poll=screen.getByLabelText("Poll interval (seconds)"); await user.clear(poll); await user.type(poll,"15");
  const rescues=screen.getByLabelText("Maximum cap rescues"); await user.clear(rescues); await user.type(rescues,"6");
  await user.click(screen.getByLabelText("Notify group: progress")); await user.click(screen.getByRole("button",{name:"Save settings"}));
  await screen.findByText(/Settings saved/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT"); expect(put).toBeDefined();
  const body=JSON.parse(String(put![1]!.body)); expect(body.version).toBe("version-one"); expect(body.settings.poll_seconds).toBe(15); expect(body.settings.max_cap_rescues).toBe(6); expect(body.settings.notify_groups).toEqual({owner:true,progress:true}); expect(body.settings._note).toBe("owner note"); expect(body.settings.brain_chain[0].note).toBe("first");
});

it("blocks strict routing to a worker outside the editable allow-list", async () => {
  const strict={...response,settings:{...response.settings,allow_any_worker:false}};
  renderSettings(vi.fn(async()=>new Response(JSON.stringify(strict),{status:200,headers:{"Content-Type":"application/json"}})));
  expect(await screen.findByText(/Every routed worker must be in the allowed list/)).toBeVisible();
  expect(screen.getByRole("button",{name:"Save settings"})).toBeDisabled();
});

it("allows adding a configuration note when the API omits it", async () => {
  const settingsWithoutNote={...response.settings}; delete settingsWithoutNote._note;
  const withoutNote={...response,settings:settingsWithoutNote};
  const fetchMock=vi.fn(async (_input:RequestInfo|URL, init?:RequestInit) => {
    if(init?.method==="PUT") return new Response(JSON.stringify({...withoutNote,settings:JSON.parse(String(init.body)).settings}),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify(withoutNote),{status:200,headers:{"Content-Type":"application/json"}});
  });
  renderSettings(fetchMock); const user=userEvent.setup();
  const note=await screen.findByLabelText("Configuration note"); expect(note).toHaveValue("");
  await user.type(note,"new owner note"); await user.click(screen.getByRole("button",{name:"Save settings"}));
  await screen.findByText(/Settings saved/);
  const put=fetchMock.mock.calls.find(([,init])=>init?.method==="PUT");
  expect(JSON.parse(String(put![1]!.body)).settings._note).toBe("new owner note");
});

it("uses safe defaults when an older API response omits new controls", async () => {
  const oldSettings = {...response.settings} as Partial<typeof response.settings>;
  delete oldSettings.max_work_rounds; delete oldSettings.max_cap_rescues; delete oldSettings.notify_groups;
  const oldResponse = {...response,settings:oldSettings};
  renderSettings(vi.fn(async()=>new Response(JSON.stringify(oldResponse),{status:200,headers:{"Content-Type":"application/json"}})));
  expect(await screen.findByLabelText("Maximum work rounds")).toHaveValue(3);
  expect(screen.getByLabelText("Maximum cap rescues")).toHaveValue(2);
  expect(screen.getByLabelText("Notify group: owner")).toBeChecked();
  expect(screen.getByRole("button",{name:"Save settings"})).toBeEnabled();
});
