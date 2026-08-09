import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Dialog } from "./Dialog";

const models={models:[{model:"same",provider:"openai",note:"Первая модель"},{model:"same",provider:"anthropic",note:"Вторая модель"}]};

it("selects a configured model and sends the full multi-turn history",async()=>{
  const requests: Array<{brain_index:number;messages:Array<{role:string;content:string}>}>=[];
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(String(input).includes("models")) return new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}});
    const body=JSON.parse(String(init?.body)); requests.push(body);
    return new Response(JSON.stringify({message:{role:"assistant",content:requests.length===1?"Ответ один":"Ответ два"},model_label:"Вторая модель"}),{status:200,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup();
  const select=await screen.findByLabelText("Модель для диалога"); await user.click(select); await user.click(screen.getAllByRole("option")[1]);
  const input=screen.getByLabelText("Ваш вопрос"); await user.type(input,"Первый вопрос"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByText("Ответ один")).toBeVisible(); await user.type(input,"Второй вопрос"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByText("Ответ два")).toBeVisible(); expect(requests[1]).toEqual({brain_index:1,messages:[{role:"user",content:"Первый вопрос"},{role:"assistant",content:"Ответ один"},{role:"user",content:"Второй вопрос"}]});
});

it("shows a useful message when the selected model is rate limited",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    if(String(input).includes("models")) return new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}});
    return new Response(JSON.stringify({error:{code:"dialog_rate_limited",message:"Лимит выбранной модели исчерпан. Попробуйте позже или выберите другую модель"}}),{status:429,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup(); const input=await screen.findByLabelText("Ваш вопрос"); await user.type(input,"Ответь"); await user.click(screen.getByRole("button",{name:"Отправить"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Лимит выбранной модели исчерпан"); expect(input).toHaveValue("Ответь");
});

it("blocks duplicate sends and preserves the question for retry after an error",async()=>{
  let resolveRequest:(value:Response)=>void=()=>{}; let attempts=0;
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    if(String(input).includes("models")) return new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}});
    attempts++; if(attempts===1) return new Promise<Response>(resolve=>{resolveRequest=resolve;});
    return new Response(JSON.stringify({message:{role:"assistant",content:"Получилось"},model_label:"Первая модель"}),{status:200,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup(); const input=await screen.findByLabelText("Ваш вопрос"); await user.type(input,"Не потеряй меня"); const send=screen.getByRole("button",{name:"Отправить"}); await user.click(send); expect(screen.getByRole("button",{name:"Модель думает…"})).toBeDisabled(); await user.click(send); expect(attempts).toBe(1);
  resolveRequest(new Response(JSON.stringify({error:{code:"dialog_failed",message:"Не удалось получить ответ модели. Попробуйте ещё раз"}}),{status:502,headers:{"Content-Type":"application/json"}}));
  expect(await screen.findByRole("alert")).toBeVisible(); expect(input).toHaveValue("Не потеряй меня"); await user.click(screen.getByRole("button",{name:"Повторить"})); await waitFor(()=>expect(attempts).toBe(2)); expect(await screen.findByText("Получилось")).toBeVisible();
});

it("previews a screenshot and sends its bytes with the question",async()=>{
  let sent: {screenshot?:{name:string;content_type:string;data:string}}={};
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(String(input).includes("models")) return new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}});
    sent=JSON.parse(String(init?.body));
    return new Response(JSON.stringify({message:{role:"assistant",content:"Вижу"},model_label:"Первая модель"}),{status:200,headers:{"Content-Type":"application/json"}});
  }));
  render(<Dialog/>); const user=userEvent.setup();
  await screen.findByLabelText("Модель для диалога");
  const file=new File([new Uint8Array([137,80,78,71])],"screen.png",{type:"image/png"});
  await user.upload(screen.getByLabelText("Скриншот к вопросу"),file);
  expect(await screen.findByAltText("Скриншот: screen.png")).toBeVisible();
  await user.type(screen.getByLabelText("Ваш вопрос"),"Что здесь?");
  await user.click(screen.getByRole("button",{name:"Отправить"}));
  await screen.findByText("Вижу");
  expect(sent.screenshot).toEqual({name:"screen.png",content_type:"image/png",data:"iVBORw=="});
  expect(screen.queryByAltText("Скриншот: screen.png")).not.toBeInTheDocument();
});

it("captures the approved stand in the server browser and attaches it",async()=>{
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{
    if(String(input).includes("models")) return new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}});
    if(String(input).includes("browser/capture")) return new Response(JSON.stringify({url:"https://staging-automation.tarser.net/orders",content_type:"image/png",data:"iVBORw=="}),{status:200,headers:{"Content-Type":"application/json"}});
    throw new Error("unexpected request");
  }));
  render(<Dialog/>); const user=userEvent.setup();
  const address=await screen.findByLabelText("Адрес страницы стенда");
  await user.clear(address); await user.type(address,"https://staging-automation.tarser.net/orders");
  await user.click(screen.getByRole("button",{name:"Посмотреть стенд"}));
  expect(await screen.findByAltText("Скриншот: стенд.png")).toBeVisible();
});

it("waits for the latest screenshot selection before sending",async()=>{
  const readers: Array<{result:string|null;onload:(()=>void)|null}>=[];
  const OriginalFileReader=globalThis.FileReader;
  class DeferredFileReader {
    result:string|null=null;
    onload:(()=>void)|null=null;
    onerror:(()=>void)|null=null;
    constructor(){ readers.push(this); }
    readAsDataURL() {}
  }
  vi.stubGlobal("FileReader",DeferredFileReader);
  try {
    vi.stubGlobal("fetch",vi.fn(async()=>new Response(JSON.stringify(models),{status:200,headers:{"Content-Type":"application/json"}})));
    render(<Dialog/>); const user=userEvent.setup();
    await screen.findByLabelText("Модель для диалога");
    const input=screen.getByLabelText("Скриншот к вопросу");
    await user.upload(input,new File(["old"],"old.png",{type:"image/png"}));
    await user.upload(input,new File(["new"],"new.png",{type:"image/png"}));
    await user.type(screen.getByLabelText("Ваш вопрос"),"Что здесь?");
    expect(screen.getByRole("button",{name:"Читаем скриншот…"})).toBeDisabled();
    readers[0].result="data:image/png;base64,b2xk"; readers[0].onload?.();
    expect(screen.queryByAltText("Скриншот: old.png")).not.toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Читаем скриншот…"})).toBeDisabled();
    readers[1].result="data:image/png;base64,bmV3"; readers[1].onload?.();
    expect(await screen.findByAltText("Скриншот: new.png")).toBeVisible();
    expect(screen.getByRole("button",{name:"Отправить"})).toBeEnabled();
  } finally {
    vi.stubGlobal("FileReader",OriginalFileReader);
  }
});
