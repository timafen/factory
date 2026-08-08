import { Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { SpeakButton } from "./Speak";

/** Plain-language verdict for a stage result: shown above the technical output. */
export function VerdictBox({ taskId, title, raw }: { taskId: string; title: string; raw?: string }) {
  const [verdict, setVerdict] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [tried, setTried] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const r = await fetch(`/api/v1/verdicts/${taskId}`);
        if (!r.ok) return;
        const d = (await r.json()) as { verdict?: string };
        if (live && d.verdict) setVerdict(d.verdict);
      } catch { /* ignore */ } finally {
        if (live) setTried(true);
      }
    })();
    return () => { live = false; };
  }, [taskId]);

  const explain = async () => {
    setLoading(true);
    try {
      const r = await fetch("/intake/explain-result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: raw ?? "", title }),
      });
      const d = (await r.json()) as { verdict?: string };
      if (d.verdict) setVerdict(d.verdict);
    } finally {
      setLoading(false);
    }
  };

  if (!verdict && !tried) return null;

  return (
    <div style={{
      background: "#16241c", border: "1px solid #2f5741", borderRadius: 10,
      padding: "12px 14px", margin: "0 0 12px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: verdict ? 6 : 0 }}>
        <Sparkles size={15} color="#7ee2a8" />
        <strong style={{ color: "#7ee2a8", fontSize: 13 }}>Что произошло, по-русски</strong>
        {verdict && <SpeakButton text={verdict} label="Вслух" />}
        <span style={{ flex: 1 }} />
        {!verdict && raw && (
          <button className="button" style={{ fontSize: 12, padding: "2px 10px" }}
                  onClick={() => void explain()} disabled={loading}>
            {loading ? <Loader2 size={13} className="spin" /> : null} Объяснить
          </button>
        )}
      </div>
      {verdict
        ? <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5 }}>{verdict}</p>
        : <span style={{ fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>
            Понятного объяснения ещё нет — нажми «Объяснить».
          </span>}
    </div>
  );
}
