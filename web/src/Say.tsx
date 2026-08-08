import { Mic, Square, Loader2, CheckCircle2, RotateCcw, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { SpeakButton, speakText, cancelSpeech, cleanForSpeech, unlockAudio } from "./Speak";

type Subtask = { title: string; detail?: string; complexity?: string };
type Proposal = {
  mode: "task" | "epic" | "answer";
  repository_id: string;
  title?: string;
  summary?: string;
  transcript?: string;
  task?: Subtask;
  subtasks?: Subtask[];
};
type CommitResult = {
  mode: string;
  task_id?: string;
  epic_id?: string;
  started?: boolean;
  detail?: string;
  children?: { task_id?: string; title?: string; complexity?: string }[];
};

type Phase = "idle" | "recording" | "transcribing" | "review" | "dispatching" | "proposal" | "committing" | "done";

export function SayView() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [transcript, setTranscript] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refining, setRefining] = useState<null | "rec" | "stt" | "think">(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const refineFlag = useRef(false);
  const refineIntent = useRef<"edit" | "ask">("edit");

  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [speaking, setSpeaking] = useState(false);
  const [autoRead, setAutoRead] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number>(0);

  const stopSpeaking = () => {
    cancelSpeech();
    setSpeaking(false);
  };

  /** iOS unlocks speech output only inside a user tap; call this on the mic tap. */
  const unlockSpeech = () => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    synth.getVoices(); // kick off async voice loading
    try {
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0;
      synth.speak(u);
    } catch { /* ignore */ }
  };

  const speak = (text: string) => {
    if (!text.trim()) return;
    setSpeaking(true);
    speakText(text, () => setSpeaking(false));
  };

  const startWave = (stream: MediaStream) => {
    const AC: typeof AudioContext | undefined =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    const canvas = canvasRef.current;
    if (!AC || !canvas) return;
    const ctx = new AC();
    audioCtxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const g = canvas.getContext("2d");
    const draw = () => {
      if (!g) return;
      analyser.getByteTimeDomainData(data);
      const { width: w, height: h } = canvas;
      g.clearRect(0, 0, w, h);
      const bars = 48;
      const step = Math.floor(data.length / bars);
      const bw = w / bars;
      for (let i = 0; i < bars; i++) {
        let peak = 0;
        for (let j = 0; j < step; j++) peak = Math.max(peak, Math.abs(data[i * step + j] - 128));
        const bh = Math.max(3, (peak / 128) * h);
        g.fillStyle = "#8ec5ff";
        g.fillRect(i * bw + bw * 0.2, (h - bh) / 2, bw * 0.6, bh);
      }
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);
  };

  const stopWave = () => {
    cancelAnimationFrame(rafRef.current);
    void audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
  };

  const proposalToSpeech = (p: Proposal): string => {
    const parts: string[] = [];
    if (p.mode === "epic") {
      parts.push(`Это эпик: ${p.title || ""}.`);
      if (p.summary) parts.push(p.summary);
      const subs = p.subtasks || [];
      parts.push(`План из ${subs.length} подзадач.`);
      subs.forEach((s, i) => {
        parts.push(`${i + 1}. ${s.title}. Сложность: ${cxRu(s.complexity)}.`);
      });
      parts.push("Скажу честно: запуск только после твоего подтверждения. Нажми «Запустить эпик», если план подходит.");
    } else {
      parts.push(`Это одна задача: ${p.task?.title || p.title || ""}.`);
      if (p.summary) parts.push(p.summary);
      if (p.task?.detail) parts.push(p.task.detail);
      parts.push(`Сложность: ${cxRu(p.task?.complexity)}. Нажми «Запустить задачу», если всё верно.`);
    }
    return parts.join(" ");
  };

  useEffect(() => () => stopWave(), []);

  // auto-read the proposal aloud when it arrives (for hands-free use)
  useEffect(() => {
    if (phase === "proposal" && proposal && autoRead) {
      speak(proposalToSpeech(proposal));
    }
    if (phase !== "proposal") stopSpeaking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, proposal]);

  const reset = () => {
    stopSpeaking();
    refineFlag.current = false;
    setRefining(null);
    setAnswer(null);
    setPhase("idle");
    setTranscript("");
    setProposal(null);
    setResult(null);
    setError(null);
  };

  const startRecording = async () => {
    setError(null);
    unlockSpeech(); // user gesture: unlock iOS speech output for later auto-read
    unlockAudio();  // and unlock audio playback for the server voice
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        stopWave();
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        if (refineFlag.current) {
          void refineFromAudio(blob);
        } else {
          void transcribe(blob);
        }
      };
      mediaRef.current = rec;
      rec.start();
      if (!refineFlag.current) setPhase("recording");
      window.setTimeout(() => startWave(stream), 50);
    } catch (e) {
      setError("Нет доступа к микрофону. Разреши доступ в браузере и попробуй снова.");
      if (refineFlag.current) { refineFlag.current = false; setRefining(null); }
      else setPhase("idle");
    }
  };

  const stopRecording = () => {
    mediaRef.current?.stop();
    if (refineFlag.current) setRefining("stt");
    else setPhase("transcribing");
  };

  const startRefine = async (intent: "edit" | "ask") => {
    stopSpeaking();
    refineFlag.current = true;
    refineIntent.current = intent;
    setAnswer(null);
    setRefining("rec");
    await startRecording();
  };

  const refineFromAudio = async (blob: Blob) => {
    try {
      const fd = new FormData();
      fd.append("audio", blob, "refine.webm");
      const r = await fetch("/intake/transcribe", { method: "POST", body: fd });
      if (!r.ok) throw new Error(`stt ${r.status}`);
      const said = ((await r.json()) as { text: string }).text?.trim();
      if (!said) throw new Error("empty");
      setRefining("think");
      const r2 = await fetch("/intake/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: said, proposal, intent: refineIntent.current }),
      });
      if (!r2.ok) throw new Error(`refine ${r2.status}`);
      const data = await r2.json() as (Omit<Proposal, "mode"> & { answer?: string; mode: string });
      if (data.mode === "answer") {
        setAnswer(data.answer || "");
        speak(data.answer || "");
      } else {
        setProposal(data as Proposal);
        setAnswer(null);
        // useEffect on proposal change auto-reads the revised plan
      }
    } catch (e) {
      setError("Не получилось уточнить. Скажи ещё раз.");
    } finally {
      refineFlag.current = false;
      setRefining(null);
    }
  };

  const transcribe = async (blob: Blob) => {
    try {
      const fd = new FormData();
      fd.append("audio", blob, "say.webm");
      const r = await fetch("/intake/transcribe", { method: "POST", body: fd });
      if (!r.ok) throw new Error(`transcribe ${r.status}`);
      const data = (await r.json()) as { text: string };
      setTranscript(data.text || "");
      setPhase("review");
    } catch (e) {
      setError("Не удалось распознать речь. Попробуй ещё раз.");
      setPhase("idle");
    }
  };

  const dispatch = async () => {
    if (!transcript.trim()) return;
    setPhase("dispatching");
    setError(null);
    try {
      const r = await fetch("/intake/dispatch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: transcript }),
      });
      if (!r.ok) throw new Error(`dispatch ${r.status}`);
      setProposal((await r.json()) as Proposal);
      setPhase("proposal");
    } catch (e) {
      setError("Диспетчер не смог разобрать задачу. Поправь текст и попробуй снова.");
      setPhase("review");
    }
  };

  const commit = async () => {
    if (!proposal) return;
    setPhase("committing");
    setError(null);
    try {
      const r = await fetch("/intake/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal }),
      });
      if (!r.ok) throw new Error(`commit ${r.status}`);
      const res = (await r.json()) as CommitResult;
      setResult(res);
      setPhase("done");
      if (autoRead) {
        window.setTimeout(() => speak(
          res.mode === "epic"
            ? `Готово. Эпик запущен, ${res.children?.length ?? 0} подзадач ушли в работу.`
            : "Готово. Задача создана и пошла по конвейеру."
        ), 100);
      }
    } catch (e) {
      setError("Не удалось завести задачу. Попробуй ещё раз.");
      setPhase("proposal");
    }
  };

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
      <p style={{ color: "var(--text-muted, #8a94a6)", margin: 0 }}>
        Нажми на микрофон и скажи, что нужно сделать. Дальше система сама поймёт — одна это задача или
        эпик из нескольких — покажет план, и запустит после твоего подтверждения.
        <span style={{ display: "block", marginTop: 6, fontSize: 11, opacity: 0.6 }}>
          build v12 · правки и вопросы раздельно{typeof window !== "undefined" && window.speechSynthesis ? "" : " · синтез речи недоступен в этом браузере"}
        </span>
      </p>

      {/* Mic control */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "24px 0" }}>
        {phase === "recording" ? (
          <button className="button button-primary" style={micStyle} onClick={stopRecording} aria-label="Остановить запись">
            <Square size={30} />
          </button>
        ) : (
          <button
            className="button button-primary"
            style={micStyle}
            onClick={startRecording}
            disabled={phase === "transcribing" || phase === "dispatching" || phase === "committing"}
            aria-label="Начать запись"
          >
            {phase === "transcribing" || phase === "dispatching" || phase === "committing" ? (
              <Loader2 size={30} className="spin" />
            ) : (
              <Mic size={30} />
            )}
          </button>
        )}
        <canvas
          ref={canvasRef}
          width={560}
          height={64}
          style={{ width: "100%", maxWidth: 560, height: 64, display: phase === "recording" ? "block" : "none" }}
        />
        <span style={{ color: "var(--text-muted, #8a94a6)", fontSize: 14 }}>
          {phase === "idle" && "Готов слушать"}
          {phase === "recording" && "Записываю… нажми, чтобы остановить"}
          {phase === "transcribing" && "Распознаю речь…"}
          {phase === "dispatching" && "Обдумываю (Fable)…"}
          {phase === "committing" && "Завожу задачу…"}
          {phase === "review" && "Проверь текст и нажми «Понять»"}
          {phase === "proposal" && "Проверь план и подтверди"}
          {phase === "done" && "Готово"}
        </span>
      </div>

      {error && (
        <div style={{ background: "#3b1d1d", color: "#ffb4b4", padding: "10px 14px", borderRadius: 8 }}>{error}</div>
      )}

      {/* Transcript review */}
      {(phase === "review" || phase === "dispatching") && (
        <div style={panelStyle}>
          <label style={{ fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
            Распознанный текст (можно поправить)
            <SpeakButton text={transcript} label="Прочитать" />
          </label>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={4}
            style={textareaStyle}
          />
          <div style={{ display: "flex", gap: 10 }}>
            <button className="button button-primary" onClick={dispatch} disabled={phase === "dispatching" || !transcript.trim()}>
              {phase === "dispatching" ? <Loader2 size={16} className="spin" /> : null} Понять
            </button>
            <button className="button" onClick={reset}>
              <RotateCcw size={15} /> Заново
            </button>
          </div>
        </div>
      )}

      {/* Proposal */}
      {(phase === "proposal" || phase === "committing") && proposal && (
        <div style={panelStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={badgeStyle}>{proposal.mode === "epic" ? "ЭПИК" : "ЗАДАЧА"}</span>
            <strong>{proposal.title}</strong>
          </div>
          {proposal.summary && <p style={{ margin: "4px 0", color: "var(--text-muted, #8a94a6)" }}>{proposal.summary}</p>}

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {speaking ? (
              <button className="button" onClick={stopSpeaking}>
                <VolumeX size={16} /> Остановить чтение
              </button>
            ) : (
              <button className="button" onClick={() => speak(proposalToSpeech(proposal))}>
                <Volume2 size={16} /> Прочитать вслух
              </button>
            )}
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
              <input type="checkbox" checked={autoRead} onChange={(e) => setAutoRead(e.target.checked)} />
              читать автоматически
            </label>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            {refining === "rec" ? (
              <button className="button" onClick={stopRecording} style={{ borderColor: "#ff9d9d" }}>
                <Square size={15} /> Стоп — я сказал{refineIntent.current === "ask" ? " (вопрос)" : " (правки)"}
              </button>
            ) : refining ? (
              <button className="button" disabled>
                <Loader2 size={15} className="spin" /> {refining === "stt" ? "Распознаю…" : "Думаю…"}
              </button>
            ) : (
              <>
                <button className="button" onClick={() => void startRefine("edit")} disabled={phase === "committing"}>
                  <Mic size={15} /> Наговорить правки
                </button>
                <button className="button" onClick={() => void startRefine("ask")} disabled={phase === "committing"}>
                  <Mic size={15} /> Задать вопрос
                </button>
              </>
            )}
          </div>

          {answer && (
            <div style={{ background: "#1c2733", border: "1px solid #2c3a4a", borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 12, color: "#8ec5ff", marginBottom: 4 }}>Ответ диспетчера</div>
              <p style={{ margin: 0, fontSize: 14 }}>{answer}</p>
            </div>
          )}

          <details style={{ fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
            <summary>Текст озвучки (что именно будет прочитано)</summary>
            <p style={{ marginTop: 6 }}>{cleanForSpeech(proposalToSpeech(proposal))}</p>
          </details>

          {proposal.mode === "task" && proposal.task && (
            <div style={itemStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong>{proposal.task.title}</strong>
                <span style={cxStyle(proposal.task.complexity)}>{proposal.task.complexity}</span>
              </div>
              {proposal.task.detail && <p style={detailStyle}>{proposal.task.detail}</p>}
            </div>
          )}

          {proposal.mode === "epic" && (proposal.subtasks || []).map((s, i) => (
            <div key={i} style={itemStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <strong>{i + 1}. {s.title}</strong>
                <span style={cxStyle(s.complexity)}>{s.complexity}</span>
              </div>
              {s.detail && <p style={detailStyle}>{s.detail}</p>}
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
            <button className="button button-primary" onClick={commit} disabled={phase === "committing"}>
              {phase === "committing" ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}{" "}
              {proposal.mode === "epic" ? "Запустить эпик" : "Запустить задачу"}
            </button>
            <button className="button" onClick={reset} disabled={phase === "committing"}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Done */}
      {phase === "done" && result && (
        <div style={panelStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#7ee2a8" }}>
            <CheckCircle2 size={18} /> <strong>Заведено и запущено</strong>
          </div>
          {result.mode === "task" && <p>Задача создана и пошла по конвейеру.</p>}
          {result.mode === "epic" && (
            <p>Эпик запущен: {result.children?.length ?? 0} подзадач ушли в конвейер. {result.detail}</p>
          )}
          <button className="button button-primary" onClick={reset}>
            <Mic size={16} /> Сказать ещё
          </button>
        </div>
      )}
    </div>
  );
}

const micStyle: CSSProperties = {
  width: 96, height: 96, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
};
const panelStyle: CSSProperties = {
  display: "flex", flexDirection: "column", gap: 10, background: "var(--surface, #171b24)",
  border: "1px solid var(--border, #262c38)", borderRadius: 12, padding: 16,
};
const textareaStyle: CSSProperties = {
  width: "100%", background: "var(--surface-2, #0f131a)", color: "inherit",
  border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: 10, fontFamily: "inherit", fontSize: 15, resize: "vertical",
};
const itemStyle: CSSProperties = {
  background: "var(--surface-2, #0f131a)", border: "1px solid var(--border, #262c38)", borderRadius: 8, padding: "10px 12px",
};
const detailStyle: CSSProperties = { margin: "6px 0 0", fontSize: 14, color: "var(--text-muted, #8a94a6)" };
const badgeStyle: CSSProperties = {
  fontSize: 11, fontWeight: 700, letterSpacing: 0.5, padding: "2px 8px", borderRadius: 999,
  background: "#22303f", color: "#8ec5ff",
};
function cxStyle(cx?: string): CSSProperties {
  const color = cx === "high" ? "#ff9d9d" : cx === "low" ? "#9fe0b0" : "#e0cf9f";
  return { fontSize: 12, color, whiteSpace: "nowrap" };
}
function cxRu(cx?: string): string {
  if (cx === "high") return "высокая";
  if (cx === "low") return "низкая";
  return "средняя";
}
