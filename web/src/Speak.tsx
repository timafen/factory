import { Volume2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";

/* ---- speech: server-side neural TTS (Piper), browser voice as fallback ---- */

type Lang = "ru" | "en";

function detectLang(text: string): Lang {
  const cyr = (text.match(/[а-яё]/gi) || []).length;
  const lat = (text.match(/[a-z]/gi) || []).length;
  return cyr >= lat ? "ru" : "en";
}

/** Whitelist cleaner: keep only letters (any language), digits, whitespace and
 *  readable punctuation. Backslashes, braces, quotes, escape artifacts can
 *  never survive this. Exported so the UI can SHOW what will be spoken. */
// eslint-disable-next-line react-refresh/only-export-components
export function cleanForSpeech(text: string): string {
  try {
    return text
      .replace(/```[\s\S]*?```/g, ". Дальше блок кода, пропускаю. ")
      .replace(/[^\p{L}\p{N}\s.,!?;:()«»—-]/gu, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 4000);
  } catch {
    return text
      .replace(/```[\s\S]*?```/g, ". дальше блок кода. ")
      .replace(/[\\{}[\]"'`*_#>|~^=+/<]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 4000);
  }
}

let sharedAudio: HTMLAudioElement | null = null;
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

/** Fire-and-forget telemetry so speech problems can be debugged from the server. */
// eslint-disable-next-line react-refresh/only-export-components
export function speechLog(event: string, detail = ""): void {
  try {
    void fetch("/intake/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, detail: detail.slice(0, 400) }),
    }).catch(() => undefined);
  } catch { /* ignore */ }
}

/** Must be called inside a user tap once (iOS unlocks audio only in a gesture). */
// eslint-disable-next-line react-refresh/only-export-components
export function unlockAudio(): void {
  if (!sharedAudio) sharedAudio = new Audio();
  sharedAudio.src = SILENT_WAV;
  void sharedAudio.play().catch(() => undefined);
  window.speechSynthesis?.getVoices();
}

function browserSpeak(clean: string, onDone?: () => void): void {
  const synth = window.speechSynthesis;
  if (!synth) { onDone?.(); return; }
  synth.cancel();
  const lang = detectLang(clean);
  const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang));
  const u = new SpeechSynthesisUtterance(clean);
  if (voices.length) u.voice = voices[0];
  u.lang = lang === "ru" ? "ru-RU" : "en-US";
  u.rate = 0.97;
  u.onend = () => onDone?.();
  u.onerror = () => onDone?.();
  synth.speak(u);
}

/** Speak via the server (neural voice, same on every device); falls back to the
 *  browser voice if the server is unreachable. */
// eslint-disable-next-line react-refresh/only-export-components
export function speakText(text: string, onDone?: () => void): void {
  const clean = cleanForSpeech(text);
  if (!clean) { onDone?.(); return; }
  speechLog("speak-start", `bs=${clean.includes("\\") ? "YES" : "no"} :: ${clean.slice(0, 120)}`);
  cancelSpeech();
  void (async () => {
    try {
      const r = await fetch("/intake/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: clean }),
      });
      if (!r.ok) throw new Error(`tts http ${r.status}`);
      const meta = (await r.json()) as { id: string; bytes: number };
      if (!sharedAudio) sharedAudio = new Audio();
      sharedAudio.onended = () => { onDone?.(); };
      sharedAudio.onerror = () => { speechLog("audio-error", sharedAudio?.error?.message ?? "?"); onDone?.(); };
      sharedAudio.src = `/intake/tts-audio/${meta.id}`;
      await sharedAudio.play();
      speechLog("server-voice-playing", `mp3 ${Math.round(meta.bytes / 1024)}KB via url`);
    } catch (e) {
      speechLog("fallback-browser-voice", String(e).slice(0, 150));
      browserSpeak(clean, onDone);
    }
  })();
}

// eslint-disable-next-line react-refresh/only-export-components
export function cancelSpeech(): void {
  if (sharedAudio) {
    sharedAudio.pause();
    sharedAudio.onended = null;
    sharedAudio.onerror = null;
  }
  window.speechSynthesis?.cancel();
}

/* ---- small "read aloud" button for any text ---- */

export function SpeakButton({ text, label }: { text?: string | null; label?: string }) {
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => () => cancelSpeech(), []);
  if (!text) return null;

  const toggle = () => {
    if (speaking) { cancelSpeech(); setSpeaking(false); return; }
    unlockAudio(); // we're inside a tap: unlock playback for iOS
    setSpeaking(true);
    speakText(text, () => setSpeaking(false));
  };

  return (
    <button
      className="button"
      style={{ padding: "2px 10px", fontSize: 12, marginLeft: 8, verticalAlign: "middle" }}
      onClick={toggle}
      title="Прочитать вслух"
    >
      {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />} {speaking ? "Стоп" : (label ?? "Вслух")}
    </button>
  );
}
