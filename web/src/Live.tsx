import { Activity, Loader2, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type Ev = { sequence: number; kind?: string; payload?: unknown; created_at?: string };

/** What is the agent doing RIGHT NOW. Polls only while switched on, so an idle
 *  screen costs nothing. */
export function LiveActivity({ attemptId, running }: { attemptId?: string; running: boolean }) {
  const [on, setOn] = useState(false);
  const [lines, setLines] = useState<{ t: string; text: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const after = useRef(0);
  const boxRef = useRef<HTMLDivElement | null>(null);

  const pull = async () => {
    if (!attemptId) return;
    setLoading(true);
    try {
      const r = await fetch(`/api/v1/attempts/${attemptId}/events?after=${after.current}&limit=100`);
      if (!r.ok) return;
      const d = (await r.json()) as { events?: Ev[] };
      const evs = d.events ?? [];
      if (evs.length) {
        after.current = evs[evs.length - 1].sequence;
        const add = evs.map((e) => ({
          t: e.created_at ? new Date(e.created_at).toLocaleTimeString("ru-RU") : "",
          text: humanise(e),
        })).filter((x) => x.text);
        setLines((cur) => [...cur, ...add].slice(-200));
      }
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!on) return;
    // The first request is part of starting the explicitly enabled poller.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void pull();
    const h = window.setInterval(() => void pull(), 3000);
    return () => window.clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, attemptId]);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines]);

  if (!attemptId) return null;

  return (
    <section className="panel">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Activity size={16} color={running ? "#8ec5ff" : "#8a94a6"} />
        <strong>Что делает агент прямо сейчас</strong>
        {running && <span style={{ fontSize: 12, color: "#8ec5ff" }}>● в работе</span>}
        <span style={{ flex: 1 }} />
        <button className="button" onClick={() => setOn((v) => !v)}>
          {on ? <><Pause size={14} /> Остановить показ</> : <><Play size={14} /> Показать вживую</>}
        </button>
      </div>

      {on && (
        <div
          ref={boxRef}
          style={{
            marginTop: 10, maxHeight: 320, overflowY: "auto",
            background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)",
            borderRadius: 8, padding: "10px 12px", fontSize: 13, lineHeight: 1.5,
          }}
        >
          {lines.length === 0 && (
            <div style={{ color: "var(--text-muted, #8a94a6)" }}>
              {loading ? "Подключаюсь…" : "Пока тихо — агент ещё не прислал шагов."}
            </div>
          )}
          {lines.map((l, i) => (
            <div key={i} style={{ display: "flex", gap: 8 }}>
              <span style={{ color: "#4d5a6b", fontVariantNumeric: "tabular-nums" }}>{l.t}</span>
              <span>{l.text}</span>
            </div>
          ))}
          {loading && <Loader2 size={13} className="spin" />}
        </div>
      )}
      {!on && (
        <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
          Ничего не опрашивается, пока не нажмёшь — экран не тратит ресурсы впустую.
        </p>
      )}
    </section>
  );
}

/** Turn a raw Claude Code event into one readable Russian line. */
function humanise(e: Ev): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const type = String(p.type ?? "");

  if (type === "system" || type === "rate_limit_event") return "";   // noise

  if (type === "assistant" || type === "user") {
    const msg = (p.message ?? {}) as Record<string, unknown>;
    const content = Array.isArray(msg.content) ? (msg.content as Record<string, unknown>[]) : [];
    const out: string[] = [];
    for (const c of content) {
      const ct = String(c.type ?? "");
      if (ct === "text") {
        const t = String(c.text ?? "").trim();
        if (t) out.push(t.slice(0, 300));
      } else if (ct === "thinking") {
        const t = String(c.thinking ?? "").trim();
        out.push(t ? `🧠 ${t.slice(0, 200)}` : "🧠 обдумывает…");
      } else if (ct === "tool_use") {
        out.push(toolLine(String(c.name ?? ""), (c.input ?? {}) as Record<string, unknown>));
      } else if (ct === "tool_result") {
        const raw = typeof c.content === "string" ? c.content : JSON.stringify(c.content ?? "");
        const first = raw.split("\n").filter(Boolean)[0] ?? "";
        if (first) out.push(`↳ ${first.slice(0, 160)}`);
      }
    }
    return out.join("  ");
  }

  if (type === "result") {
    const r = String(p.subtype ?? p.result ?? "");
    return `✅ этап завершён${r ? ` (${r})` : ""}`;
  }
  return "";
}

function toolLine(name: string, input: Record<string, unknown>): string {
  const s = (v: unknown) => (typeof v === "string" ? v : "");
  const cmd = s(input.command), file = s(input.file_path) || s(input.path);
  const pat = s(input.pattern) || s(input.query);
  switch (name) {
    case "Bash":      return `⚙️ команда: ${cmd.slice(0, 180)}`;
    case "Read":      return `📖 читает ${file}`;
    case "Write":     return `✍️ пишет ${file}`;
    case "Edit":      return `✏️ правит ${file}`;
    case "Glob":      return `🔍 ищет файлы: ${pat}`;
    case "Grep":      return `🔍 ищет по коду: ${pat}`;
    case "WebSearch": return `🌐 ищет в интернете: ${pat}`;
    case "WebFetch":  return `🌐 открывает ${s(input.url)}`;
    case "TodoWrite": return "📋 обновляет свой план";
    case "Task":      return `👥 запускает помощника: ${s(input.description)}`;
    default:          return `🔧 ${name}${file || cmd ? `: ${(file || cmd).slice(0, 140)}` : ""}`;
  }
}
