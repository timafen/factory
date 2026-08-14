import { Brain, Loader2, Mic, Send, Square, Trash2, RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useVisibleInterval } from "./polling";
import { SpeakButton, unlockAudio } from "./Speak";
import { ProjectTag, useProjectName } from "./project";

type Question = {
  id: string;
  task_id: string;
  stage: string;
  resume_stage: string;
  title: string;
  situation?: string;
  question?: string;
  options?: string[];
  repository_id?: string;
  status: string;
  answer?: string;
  answered_by?: string;
  escalation_reason?: string;
  reservation?: { stage?: string; answered_at?: string };
};

export function AnswerView({ onTask }: { onTask?: (id: string) => void }) {
  const interval = useVisibleInterval(10_000);
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, string>>({}); // id -> phase
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingFor = useRef<string | null>(null);

  const questions = useQuery({
    queryKey: ["questions"],
    queryFn: async (): Promise<Question[]> => {
      const r = await fetch("/api/v1/questions");
      if (!r.ok) throw new Error(`questions ${r.status}`);
      return ((await r.json()).questions ?? []) as Question[];
    },
    refetchInterval: interval,
  });

  // Кто сейчас думает за оркестратора. Цепочка движков переключается сама,
  // когда кончаются токены, — надпись обязана следовать за ней, а не врать.
  const brain = useQuery({
    queryKey: ["brain-now"],
    queryFn: async (): Promise<string> => {
      const r = await fetch("/api/v1/dashboard");
      if (!r.ok) return "";
      const d = (await r.json()) as {
        brain?: { last?: { model?: string }; chain?: { model: string; blocked?: boolean }[] };
      };
      const b = d.brain;
      if (!b) return "";
      return b.last?.model || b.chain?.find((e) => !e.blocked)?.model || "";
    },
    refetchInterval: 60_000,
  });
  const engineName = brain.data || "оркестратор";

  const projectName = useProjectName();

  const setDraft = (id: string, v: string) => setDrafts((d) => ({ ...d, [id]: v }));
  const setPhase = (id: string, v: string) =>
    setBusy((b) => { const n = { ...b }; if (v) n[id] = v; else delete n[id]; return n; });

  const startRec = async (id: string) => {
    unlockAudio();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setPhase(id, "stt");
        try {
          const fd = new FormData();
          fd.append("audio", new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" }), "a.webm");
          const r = await fetch("/intake/transcribe", { method: "POST", body: fd });
          const said = ((await r.json()) as { text: string }).text || "";
          setDraft(id, ((drafts[id] || "") + " " + said).trim());
        } finally {
          setPhase(id, "");
          recordingFor.current = null;
        }
      };
      mediaRef.current = rec;
      recordingFor.current = id;
      rec.start();
      setPhase(id, "rec");
    } catch {
      setPhase(id, "");
    }
  };

  const stopRec = () => mediaRef.current?.stop();

  const askFable = async (q: Question) => {
    setPhase(q.id, "think");
    try {
      const r = await fetch("/intake/suggest-answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q.question, situation: q.situation,
          title: q.title, stage: q.stage,
          // Без этого мозг берёт факты из общего контекста и путает проекты.
          repository_id: q.repository_id ?? "",
        }),
      });
      const data = (await r.json()) as { answer?: string };
      if (data.answer) setDraft(q.id, data.answer);
    } finally {
      setPhase(q.id, "");
    }
  };

  const send = async (q: Question, selectedAnswer?: string) => {
    const answer = (selectedAnswer ?? drafts[q.id] ?? "").trim();
    if (!answer) return;
    setPhase(q.id, "send");
    try {
      await fetch(`/api/v1/questions/${q.id}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      });
      setDraft(q.id, "");
      await queryClient.invalidateQueries({ queryKey: ["questions"] });
    } finally {
      setPhase(q.id, "");
    }
  };

  const dismiss = async (q: Question) => {
    if (!window.confirm("Убрать этот вопрос из списка? Конвейер по нему не продолжится.")) return;
    await fetch(`/api/v1/questions/${q.id}`, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: ["questions"] });
  };

  const all = questions.data ?? [];
  const list = all.filter((q) => q.status === "open").reverse();
  const waiting = all.filter((q) => Boolean(q.reservation)
    && (q.status === "answered" || q.status === "no_worker")).reverse();
  const auto = all.filter((q) => q.answered_by === "orchestrator").reverse().slice(0, 12);
  const done = all.filter((q) => q.status === "resolved").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 820 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <p style={{ margin: 0, color: "var(--text-muted, #8a94a6)", flex: 1 }}>
          Здесь конвейер спрашивает тебя, когда сам решить не может. Ответь голосом или попроси
          {" "}{engineName} предложить ответ — после отправки работа продолжится сама.
          {done > 0 && ` Уже отвечено: ${done}.`}
        </p>
        <button className="button" onClick={() => void questions.refetch()}><RefreshCw size={15} /></button>
      </div>

      {questions.isPending && <div className="quiet-empty">Загружаю…</div>}
      {!questions.isPending && list.length === 0 && waiting.length === 0 && (
        <div className="quiet-empty">Вопросов к тебе нет — конвейер едет сам. 👌</div>
      )}

      {list.map((q) => {
        const phase = busy[q.id];
        const speech = `${q.title}. ${q.situation || ""} Вопрос: ${q.question || ""}`;
        return (
          <div key={q.id} style={{ background: "var(--surface, #171b24)", border: "1px solid #3a4a5f", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999, background: "#3b2f1d", color: "#e0cf9f" }}>
                {q.stage}
              </span>
              <strong style={{ fontSize: 15 }}>{q.title}</strong>
              <ProjectTag name={projectName(q.repository_id)} />
              <SpeakButton text={speech} label="Вслух" />
              <span style={{ flex: 1 }} />
              {onTask && (
                <button className="button" style={{ fontSize: 12, padding: "2px 10px" }} onClick={() => onTask(q.task_id)}>
                  Открыть задачу ›
                </button>
              )}
              <button className="button" style={{ padding: "2px 10px" }} title="Убрать" onClick={() => void dismiss(q)}>
                <Trash2 size={14} />
              </button>
            </div>

            {q.situation && <p style={{ margin: 0, fontSize: 14 }}>{q.situation}</p>}
            {q.question && (
              <p title={q.question} style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#8ec5ff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>❓ {q.question}</p>
            )}
            {q.escalation_reason && (
              <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
                Сам решить не могу: {q.escalation_reason}
              </p>
            )}

            {(q.options || []).length > 0 && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {(q.options || []).map((o, i) => (
                  <button key={i} className="button" style={{ fontSize: 12 }} onClick={() => setDraft(q.id, o)}>
                    {o}
                  </button>
                ))}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="button button-primary" onClick={() => void send(q, "Делаем")} disabled={Boolean(phase)}>
                Делаем
              </button>
              <button className="button" onClick={() => void send(q, "Не делаем")} disabled={Boolean(phase)}>
                Не делаем
              </button>
            </div>

            <textarea
              rows={3}
              placeholder="Твой ответ — можно надиктовать кнопкой ниже"
              value={drafts[q.id] || ""}
              onChange={(e) => setDraft(q.id, e.target.value)}
              style={{ width: "100%", background: "var(--surface-2, #0f131a)", color: "inherit", border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: 10, fontSize: 15, resize: "vertical" }}
            />

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {phase === "rec" ? (
                <button className="button" style={{ borderColor: "#ff9d9d" }} onClick={stopRec}>
                  <Square size={15} /> Стоп — записал
                </button>
              ) : (
                <button className="button" onClick={() => void startRec(q.id)} disabled={Boolean(phase)}>
                  {phase === "stt" ? <Loader2 size={15} className="spin" /> : <Mic size={15} />} Ответить голосом
                </button>
              )}
              <button className="button" onClick={() => void askFable(q)} disabled={Boolean(phase)}>
                {phase === "think" ? <Loader2 size={15} className="spin" /> : <Brain size={15} />} Пусть решит {engineName}
              </button>
              <button className="button button-primary" onClick={() => void send(q)} disabled={Boolean(phase) || !(drafts[q.id] || "").trim()}>
                {phase === "send" ? <Loader2 size={15} className="spin" /> : <Send size={15} />} Отправить и продолжить
              </button>
            </div>
          </div>
        );
      })}

      {waiting.length > 0 && (
        <section aria-label="Ответ принят — ожидает зарезервированный слот"
                 style={{ background: "var(--surface, #171b24)", border: "1px solid #4a3f22", borderRadius: 12, padding: 16 }}>
          <strong style={{ color: "#e0cf9f" }}>Ответ принят — ожидает зарезервированный слот</strong>
          <p style={{ margin: "7px 0 12px", fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
            Factory не ждёт нового решения: эта работа получит ближайший допустимый слот первой.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {waiting.map((q) => (
              <div key={q.id} style={{ background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: "10px 12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: "#e0cf9f" }}>{q.resume_stage || q.stage}</span>
                  <strong style={{ fontSize: 13 }}>{q.title}</strong>
                  <span style={{ flex: 1 }} />
                  {onTask && (
                    <button className="button" style={{ fontSize: 11, padding: "1px 8px" }} onClick={() => onTask(q.task_id)}>
                      задача ›
                    </button>
                  )}
                </div>
                {q.escalation_reason && (
                  <p style={{ margin: "7px 0 0", fontSize: 13, color: "#e0cf9f" }}>{q.escalation_reason}</p>
                )}
                {q.answer && <p style={{ margin: "5px 0 0", fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>Твой ответ: {q.answer}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {auto.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", color: "var(--text-muted, #8a94a6)", fontSize: 14 }}>
            Решено оркестратором без тебя ({auto.length}) — можно проверить
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
            {auto.map((q) => (
              <div key={q.id} style={{ background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: "10px 12px" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: "#8a94a6" }}>{q.stage}</span>
                  <strong style={{ fontSize: 13 }}>{q.title}</strong>
                  <SpeakButton text={`${q.title}. Вопрос: ${q.question}. Ответ оркестратора: ${q.answer}`} label="Вслух" />
                  {onTask && (
                    <button className="button" style={{ fontSize: 11, padding: "1px 8px" }} onClick={() => onTask(q.task_id)}>
                      задача ›
                    </button>
                  )}
                </div>
                <p style={{ margin: "6px 0 0", fontSize: 13, color: "#8ec5ff" }}>❓ {q.question}</p>
                <p style={{ margin: "4px 0 0", fontSize: 13 }}>🤖 {q.answer}</p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
