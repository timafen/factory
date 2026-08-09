import { useEffect, useState } from "react";
import { api, APIError } from "./api";
import type { DialogMessage } from "./types";

type ShownMessage = DialogMessage & { modelLabel?: string };

export function Dialog() {
  const [models, setModels] = useState<Array<{model:string; provider:string; note?:string}>>([]);
  const [model, setModel] = useState("");
  const [messages, setMessages] = useState<ShownMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.pilotSettings().then(({settings}) => {
      if (!active) return;
      setModels(settings.brain_chain);
      setModel(settings.brain_chain[0]?.model ?? "");
    }).catch(() => active && setError("Не удалось загрузить список моделей"));
    return () => { active = false; };
  }, []);

  const send = async () => {
    const content = question.trim();
    if (!content || !model || pending) return;
    const history: DialogMessage[] = [...messages.map(({role, content}) => ({role, content})), {role:"user", content}];
    setPending(true); setError("");
    try {
      const response = await api.dialogMessage(model, history);
      setMessages([...history, {...response.message, modelLabel:response.model_label}]);
      setQuestion("");
    } catch (cause) {
      setError(cause instanceof APIError ? cause.message : "Не удалось получить ответ модели. Попробуйте ещё раз");
    } finally { setPending(false); }
  };

  return <section className="dialog-view" aria-labelledby="dialog-title">
    <div className="page-heading"><div><h1 id="dialog-title">Диалог</h1><p>Разговор с выбранной моделью фабрики</p></div></div>
    <label className="field dialog-model">Модель
      <select aria-label="Модель для диалога" value={model} onChange={(event)=>setModel(event.target.value)} disabled={pending}>
        {models.map((item)=><option key={`${item.provider}:${item.model}`} value={item.model}>{item.note?.trim() || `${item.provider} — ${item.model}`}</option>)}
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
    <button className="button button-primary" disabled={pending || !model || !question.trim()} onClick={()=>void send()}>{pending ? "Модель думает…" : error ? "Повторить" : "Отправить"}</button>
  </section>;
}
