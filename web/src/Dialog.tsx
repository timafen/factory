import { useEffect, useRef, useState } from "react";
import { api, APIError } from "./api";
import type { DialogMessage, DialogScreenshot } from "./types";

type ShownMessage = DialogMessage & { modelLabel?: string; shot?: DialogScreenshot };
type ModelItem = { model: string; provider: string; note?: string; available?: boolean; reason?: string };

const OK_TYPES = ["image/png", "image/jpeg", "image/webp"];

/** Разбор ответа на куски: обычный текст и блоки кода в тройных кавычках. */
function parts(text: string) {
  const out: Array<{ code: boolean; lang?: string; body: string }> = [];
  const re = /```([a-zA-Z0-9+-]*)\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ code: false, body: text.slice(last, m.index) });
    out.push({ code: true, lang: m[1] || "", body: m[2] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ code: false, body: text.slice(last) });
  return out.filter((p) => p.code || p.body.trim());
}

function CodeBlock({ body, lang }: { body: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="dlg-code">
      <div className="dlg-code-head">
        <span>{lang || "код"}</span>
        <button type="button" onClick={() => {
          void navigator.clipboard?.writeText(body);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        }}>{copied ? "скопировано" : "копировать"}</button>
      </div>
      <pre><code>{body}</code></pre>
    </div>
  );
}

export function Dialog() {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [brainIndex, setBrainIndex] = useState<number | null>(null);
  const [messages, setMessages] = useState<ShownMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [screenshot, setScreenshot] = useState<DialogScreenshot | null>(null);
  const [reading, setReading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [standURL, setStandURL] = useState("https://staging-automation.tarser.net/");
  const [capturing, setCapturing] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const selection = useRef(0);

  useEffect(() => {
    let active = true;
    fetch("/api/v1/dialog/models").then((r) => r.json()).then((data) => {
      if (!active) return;
      const list: ModelItem[] = data.models || [];
      setModels(list);
      const free = list.findIndex((item) => item.available !== false);
      setBrainIndex(free >= 0 ? free : null);
      if (free < 0 && list.length) setError("Свободных моделей сейчас нет — квоты исчерпаны");
    }).catch(() => active && setError("Не удалось загрузить список моделей"));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (typeof endRef.current?.scrollIntoView === "function") {
      endRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length, pending]);

  useEffect(() => {
    const area = areaRef.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = Math.min(area.scrollHeight, 190) + "px";
  }, [question]);

  const take = (file?: File | null) => {
    if (!file) return;
    const mine = ++selection.current;
    if (!OK_TYPES.includes(file.type) || file.size > 4 * 1024 * 1024) {
      setScreenshot(null); setReading(false);
      setError("Подойдёт PNG, JPEG или WebP до 4 МБ");
      return;
    }
    setError(""); setScreenshot(null); setReading(true);
    const reader = new FileReader();
    reader.onload = () => {
      if (mine !== selection.current) return;
      setScreenshot({
        name: file.name,
        content_type: file.type as DialogScreenshot["content_type"],
        data: String(reader.result).split(",", 2)[1],
      });
      setReading(false);
    };
    reader.onerror = () => {
      if (mine !== selection.current) return;
      setReading(false); setError("Не удалось прочитать картинку, попробуйте ещё раз");
    };
    reader.readAsDataURL(file);
  };

  const send = async () => {
    const content = question.trim();
    if ((!content && !screenshot) || brainIndex === null || pending || reading) return;
    const history: DialogMessage[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: "user", content: content || "Посмотри скриншот" },
    ];
    const shown: ShownMessage[] = [
      ...messages,
      { role: "user", content: content || "Посмотри скриншот", shot: screenshot || undefined },
    ];
    setMessages(shown);
    setQuestion("");
    setPending(true); setError("");
    try {
      const response = await api.dialogMessage(brainIndex, history, screenshot || undefined);
      setMessages([...shown, { ...response.message, modelLabel: response.model_label }]);
      setScreenshot(null);
    } catch (cause) {
      setMessages(messages);
      setQuestion(content);
      setError(cause instanceof APIError ? cause.message : "Модель не ответила. Попробуйте ещё раз");
    } finally { setPending(false); }
  };

  const current = brainIndex !== null ? models[brainIndex] : undefined;
  const canSend = !pending && !reading && brainIndex !== null && (!!question.trim() || !!screenshot);

  return (
    <section className="dlg" aria-labelledby="dialog-title"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); take(e.dataTransfer.files?.[0]); }}>

      <header className="dlg-top">
        <h1 id="dialog-title">Диалог</h1>
        <div className="dlg-pick">
          <button type="button" className="dlg-chip" aria-label="Модель для диалога"
            onClick={() => setPickerOpen((v) => !v)} disabled={pending}>
            <span className="dlg-dot" />
            {current ? current.model : "выбрать модель"}
            <span className="dlg-caret">▾</span>
          </button>
          {pickerOpen && (
            <div className="dlg-menu" role="listbox">
              {models.map((item, index) => (
                <button key={index} type="button" role="option"
                  aria-selected={index === brainIndex}
                  disabled={item.available === false}
                  onClick={() => { setBrainIndex(index); setPickerOpen(false); }}>
                  <b>{item.model}</b>
                  <small>{item.available === false
                    ? (item.reason || "квота исчерпана")
                    : (item.note?.trim() || item.provider)}</small>
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="dlg-browser">
        <input aria-label="Адрес страницы стенда" value={standURL} disabled={capturing || pending}
          onChange={(event) => setStandURL(event.target.value)} />
        <button type="button" disabled={capturing || pending} onClick={async () => {
          setCapturing(true); setError("");
          try {
            const capture = await api.browserCapture(standURL);
            setStandURL(capture.url);
            setScreenshot({ name: "стенд.png", content_type: capture.content_type, data: capture.data });
          } catch (cause) {
            setError(cause instanceof APIError ? cause.message : "Не удалось открыть тестовый стенд");
          } finally { setCapturing(false); }
        }}>{capturing ? "Открываю…" : "Посмотреть стенд"}</button>
      </div>

      <div className="dlg-feed">
        {messages.length === 0 && !pending && (
          <div className="dlg-empty">
            <p>Спросите мозг фабрики о чём угодно.</p>
            <div className="dlg-hints">
              {["Что сейчас в работе?", "Почему работа крутится по кругу?", "Что стоит сделать следующим?"].map((h) => (
                <button key={h} type="button" onClick={() => { setQuestion(h); areaRef.current?.focus(); }}>{h}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => m.role === "user" ? (
          <div className="dlg-row dlg-right" key={i}>
            <div className="dlg-bubble dlg-mine">
              {m.shot && <img className="dlg-shot" src={`data:${m.shot.content_type};base64,${m.shot.data}`} alt="скриншот к вопросу" />}
              <p>{m.content}</p>
            </div>
          </div>
        ) : (
          <div className="dlg-row" key={i}>
            <div className="dlg-answer">
              <div className="dlg-who">{m.modelLabel?.split("·")[0]?.trim() || current?.model || "модель"}</div>
              {parts(m.content).map((p, k) => p.code
                ? <CodeBlock key={k} body={p.body} lang={p.lang} />
                : <p key={k}>{p.body.trim()}</p>)}
            </div>
          </div>
        ))}

        {pending && (
          <div className="dlg-row">
            <div className="dlg-answer">
              <div className="dlg-who">{current?.model || "модель"}</div>
              <div className="dlg-typing"><i /><i /><i /></div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <div className="dlg-error" role="alert">{error}</div>}

      <div className={"dlg-compose" + (dragOver ? " dlg-drag" : "")}>
        {screenshot && (
          <div className="dlg-preview">
            <img src={`data:${screenshot.content_type};base64,${screenshot.data}`} alt={`Скриншот: ${screenshot.name}`} />
            <span>{screenshot.name}</span>
            <button type="button" onClick={() => setScreenshot(null)} aria-label="Убрать скриншот">×</button>
          </div>
        )}
        {reading && <div className="dlg-preview dlg-preview-wait">читаем картинку…</div>}

        <div className="dlg-input">
          <button type="button" className="dlg-clip" title="Прикрепить скриншот"
            onClick={() => fileRef.current?.click()} disabled={pending}>📎</button>
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
            aria-label="Скриншот к вопросу"
            onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
          <textarea ref={areaRef} rows={1} value={question} disabled={pending}
            aria-label="Ваш вопрос"
            placeholder="Спросите или вставьте скриншот…"
            onChange={(e) => setQuestion(e.target.value)}
            onPaste={(e) => {
              const item = Array.from(e.clipboardData.items).find((x) => x.type.startsWith("image/"));
              if (item) { e.preventDefault(); take(item.getAsFile()); }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
            }} />
          <button type="button" className="dlg-send" disabled={!canSend}
            onClick={() => void send()}
            aria-label={pending ? "Модель думает…" : reading ? "Читаем скриншот…" : error ? "Повторить" : "Отправить"}>
            {pending ? <span className="dlg-spin" /> : "↑"}
          </button>
        </div>
        <div className="dlg-tip">Enter — отправить, Shift+Enter — перенос строки. Картинку можно перетащить или вставить.</div>
      </div>
    </section>
  );
}
