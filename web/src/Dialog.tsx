import { useEffect, useState } from "react";
import { api, APIError } from "./api";
import type { DialogMessage, DialogScreenshot } from "./types";

type ShownMessage = DialogMessage & { modelLabel?: string };

export function Dialog() {
  const [models, setModels] = useState<Array<{model:string; provider:string; note?:string; available?:boolean; reason?:string}>>([]);
  const [brainIndex, setBrainIndex] = useState<number | null>(null);
  const [messages, setMessages] = useState<ShownMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [screenshot, setScreenshot] = useState<DialogScreenshot | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/dialog/models").then((r) => r.json()).then((data) => {
      if (!active) return;
      const list = data.models || [];
      setModels(list);
      const free = list.findIndex((item: {available?:boolean}) => item.available !== false);
      setBrainIndex(free >= 0 ? free : null);
      if (free < 0 && list.length) setError("Сейчас свободных моделей нет — квоты исчерпаны");
    }).catch(() => active && setError("Не удалось загрузить список моделей"));
    return () => { active = false; };
  }, []);

  const send = async () => {
    const content = question.trim();
    if (!content || brainIndex === null || pending) return;
    const history: DialogMessage[] = [...messages.map(({role, content}) => ({role, content})), {role:"user", content}];
    setPending(true); setError("");
    try {
      const response = await api.dialogMessage(brainIndex, history, screenshot || undefined);
      setMessages([...history, {...response.message, modelLabel:response.model_label}]);
      setQuestion("");
      setScreenshot(null);
    } catch (cause) {
      setError(cause instanceof APIError ? cause.message : "Не удалось получить ответ модели. Попробуйте ещё раз");
    } finally { setPending(false); }
  };

  const chooseScreenshot = (file?: File) => {
    if (!file) return;
    if (!(["image/png", "image/jpeg", "image/webp"] as string[]).includes(file.type) || file.size > 4 * 1024 * 1024) { setError("Прикрепите PNG, JPEG или WebP размером до 4 МБ"); return; }
    const reader = new FileReader();
    reader.onload = () => setScreenshot({name:file.name, content_type:file.type as DialogScreenshot["content_type"], data:String(reader.result).split(",", 2)[1]});
    reader.readAsDataURL(file);
  };

  return <section className="dialog-view" aria-labelledby="dialog-title">
    <div className="page-heading"><div><h1 id="dialog-title">Диалог с мозгом фабрики</h1><p>Спросите по делу, приложите скриншот — и продолжайте разговор в одном месте.</p></div></div>
    <label className="field dialog-model">Модель
      <select aria-label="Модель для диалога" value={brainIndex ?? ""} onChange={(event)=>setBrainIndex(Number(event.target.value))} disabled={pending}>
        {models.map((item,index)=><option key={index} value={index} disabled={item.available === false}>{`${item.model} — ${item.provider}${item.available === false ? " · недоступна: " + (item.reason || "квота исчерпана") : (item.note?.trim() ? " · " + item.note.trim() : "")}`}</option>)}
      </select>
    </label>
    <div className="dialog-history" aria-live="polite">
      {messages.length === 0 && <p className="empty-state">Задайте первый вопрос мозгу фабрики.</p>}
      {messages.map((message,index)=><article className={`dialog-message dialog-${message.role}`} key={index}>
        <strong>{message.role === "user" ? "Вы" : message.modelLabel || "Модель"}</strong><p>{message.content}</p>
      </article>)}
    </div>
    {error && <div className="callout callout-error" role="alert">{error}</div>}
    <label className="field">Ваш вопрос
      <textarea aria-label="Ваш вопрос" value={question} onChange={(event)=>setQuestion(event.target.value)} disabled={pending}
        onKeyDown={(event)=>{ if(event.key === "Enter" && !event.shiftKey){ event.preventDefault(); void send(); } }} />
    </label>
    <div className="field"><span>Скриншот к этому вопросу <small>(необязательно)</small></span>
      <input aria-label="Скриншот к вопросу" type="file" accept="image/png,image/jpeg,image/webp" disabled={pending} onChange={(event)=>chooseScreenshot(event.target.files?.[0])} />
      {screenshot && <div className="dialog-screenshot" style={{display:"flex",alignItems:"center",gap:10,marginTop:8}}><img src={`data:${screenshot.content_type};base64,${screenshot.data}`} alt={`Скриншот: ${screenshot.name}`} style={{width:88,height:56,objectFit:"cover",borderRadius:8,border:"1px solid var(--border)"}} /><span>{screenshot.name}</span><button className="button" type="button" disabled={pending} onClick={()=>setScreenshot(null)}>Убрать</button></div>}
    </div>
    <button className="button button-primary" disabled={pending || brainIndex === null || !question.trim()} onClick={()=>void send()}>{pending ? "Модель думает…" : error ? "Повторить" : "Отправить"}</button>
  </section>;
}
