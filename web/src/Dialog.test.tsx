import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Dialog } from "./Dialog";

const settings={settings:{brain_chain:[{cli:"codex",model:"same",provider:"openai",note:"Первая модель"},{cli:"claude",model:"same",provider:"anthropic",note:"Вторая модель"}]},version:"v",warnings:[]};

it("selects a configured model and sends the full multi-turn history",async()=>{
  const requests: Array<{brain_index:number;messages:Array<{role:string;content:string}>}>=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(String(input).includes("settings")) return new Response(JSON.stringify(settings),{status:200,headers:{"Content-Type":"application/json"}});
    const body=JSON.parse(String(init?.body)); requests.push(body);
    return new Response(JSON.stringify({message:{role:"assistant",content:requests.length===1?"Ответ один":"Ответ два"},model_label:"Вторая модель"}),{status:200,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup();
  const select=await screen.findByLabelText("Модель для диалога"); expect(select).toHaveValue("0"); await user.selectOptions(select,"1");
  const input=screen.getByLabelText("Ваш вопрос"); await user.type(input,"Первый вопрос"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByText("Ответ один")).toBeVisible(); await user.type(input,"Второй вопрос"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByText("Ответ два")).toBeVisible(); expect(requests[1]).toEqual({brain_index:1,messages:[{role:"user",content:"Первый вопрос"},{role:"assistant",content:"Ответ один"},{role:"user",content:"Второй вопрос"}]});
});

it("shows a useful message when the selected model is rate limited",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    if(String(input).includes("settings")) return new Response(JSON.stringify(settings),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify({error:{code:"dialog_rate_limited",message:"Лимит выбранной модели исчерпан. Попробуйте позже или выберите другую модель"}}),{status:429,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup(); const input=await screen.findByLabelText("Ваш вопрос"); await user.type(input,"Ответь"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Лимит выбранной модели исчерпан"); expect(input).toHaveValue("Ответь");
});

it("blocks duplicate sends and preserves the question for retry after an error",async()=>{
  let resolveRequest:(value:Response)=>void=()=>{}; let attempts=0;
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    if(String(input).includes("settings")) return new Response(JSON.stringify(settings),{status:200,headers:{"Content-Type":"application/json"}});
    attempts++; if(attempts===1) return new Promise<Response>(resolve=>{resolveRequest=resolve;});
    return new Response(JSON.stringify({message:{role:"assistant",content:"Получилось"},model_label:"Первая модель"}),{status:200,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup(); const input=await screen.findByLabelText("Ваш вопрос"); await user.type(input,"Не потеряй меня"); const send=screen.getByRole("button",{name:"Отправить"}); await user.click(send); expect(screen.getByRole("button",{name:"Модель думает…"})).toBeDisabled(); await user.click(send); expect(attempts).toBe(1);
  resolveRequest(new Response(JSON.stringify({error:{code:"dialog_failed",message:"Не удалось получить ответ модели. Попробуйте ещё раз"}}),{status:502,headers:{"Content-Type":"application/json"}}));
  expect(await screen.findByRole("alert")).toBeVisible(); expect(input).toHaveValue("Не потеряй меня"); await user.click(screen.getByRole("button",{name:"Повторить"})); await waitFor(()=>expect(attempts).toBe(2)); expect(await screen.findByText("Получилось")).toBeVisible();
});
