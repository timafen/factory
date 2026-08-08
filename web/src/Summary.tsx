import { Coins, GitBranch, FileText, Loader2, Sparkles, GitPullRequest } from "lucide-react";
import { useEffect, useState } from "react";
import { SpeakButton } from "./Speak";

type Usage = {
  total_tokens: number; output: number; cache_read: number; cache_write: number;
  input: number; messages: number; model: string; cost_usd: number;
};

/** Everything the owner actually wants to know about a task, above the noise. */
export function TaskSummary({ taskId, result, error, title }: {
  taskId: string; result?: string; error?: string; title?: string;
}) {
  const [verdict, setVerdict] = useState("");
  // Адрес, где владелец увидит сделанное своими глазами.
  const [tryUrl, setTryUrl] = useState("");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const r = await fetch(`/api/v1/verdicts/${taskId}`);
        if (r.ok) {
          const d = (await r.json()) as { verdict?: string; try_url?: string };
          if (live && d.verdict) setVerdict(d.verdict);
          if (live && d.try_url) setTryUrl(d.try_url);
        }
      } catch { /* ignore */ }
      try {
        const u = await fetch(`/intake/usage/${taskId}`);
        if (u.ok) {
          const d = (await u.json()) as Usage;
          if (live && d.total_tokens > 0) setUsage(d);
        }
      } catch { /* ignore */ }
    })();
    return () => { live = false; };
  }, [taskId]);

  const explain = async () => {
    setLoading(true);
    try {
      const r = await fetch("/intake/explain-result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: result || error || "", title: title || "" }),
      });
      const d = (await r.json()) as { verdict?: string };
      if (d.verdict) setVerdict(d.verdict);
    } finally {
      setLoading(false);
    }
  };

  // artefacts pulled straight out of the agent report
  const text = `${result || ""}\n${error || ""}`;
  const branch = (text.match(/^\s*BRANCH:\s*(\S+)/m) || text.match(/\bfactory\/[A-Za-z0-9._/-]+/) || [])[1]
    ?? (text.match(/\bfactory\/[A-Za-z0-9._/-]+/) || [])[0] ?? "";
  const head = (text.match(/^\s*HEAD:\s*([0-9a-f]{7,40})/m) || [])[1] ?? "";
  const cards = [...new Set(text.match(/CARD-\d{3,4}/g) ?? [])];
  const prs = [...new Set(text.match(/https:\/\/github\.com\/[^\s)]+\/pull\/\d+/g) ?? [])];
  const verdictWord = (text.match(/\b(PASS|BLOCKED|APPROVE|REQUEST CHANGES)\b/) || [])[0] ?? "";
  // Владелец не обязан знать эти слова. Они означают судьбу работы.
  const VERDICT_RU: Record<string, string> = {
    "PASS": "проверка пройдена",
    "APPROVE": "ревью одобрило",
    "REQUEST CHANGES": "ревью вернуло на доработку",
    "BLOCKED": "работа застряла",
  };
  const verdictRu = VERDICT_RU[verdictWord] ?? verdictWord;
  const files = [...new Set(text.match(/[\w./-]+\.(?:py|ts|tsx|go|md|json|ya?ml|sh|txt)\b/g) ?? [])].slice(0, 8);

  const num = (n: number) => n.toLocaleString("ru-RU");
  const hasArtefacts = branch || head || cards.length || prs.length || files.length || verdictWord;

  return (
    <section className="panel" style={{ borderColor: "#2f5741" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <Sparkles size={16} color="#7ee2a8" />
        <strong style={{ color: "#7ee2a8" }}>Итог</strong>
        {verdictWord && (
          <span style={{
            fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
            background: /PASS|APPROVE/.test(verdictWord) ? "#16341f" : "#3b1d1d",
            color: /PASS|APPROVE/.test(verdictWord) ? "#7ee2a8" : "#ffb4b4",
          }}>{verdictRu}</span>
        )}
        {verdict && <SpeakButton text={verdict} label="Вслух" />}
        {tryUrl && (
          // «Сделано» ничего не значит, пока это нельзя открыть и потрогать.
          <a href={tryUrl} target="_blank" rel="noreferrer" className="button"
             style={{ fontSize: 12, padding: "2px 10px", textDecoration: "none" }}>
            Посмотреть →
          </a>
        )}
        <span style={{ flex: 1 }} />
        {!verdict && (result || error) && (
          <button className="button" style={{ fontSize: 12, padding: "2px 10px" }}
                  onClick={() => void explain()} disabled={loading}>
            {loading ? <Loader2 size={13} className="spin" /> : null} Объяснить по-русски
          </button>
        )}
      </div>

      {verdict
        ? <p style={{ margin: "0 0 12px", fontSize: 15, lineHeight: 1.55 }}>{verdict}</p>
        : <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
            Понятного объяснения пока нет — нажми «Объяснить по-русски».
          </p>}

      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 13 }}>
        {hasArtefacts && (
          <div style={{ minWidth: 220, flex: 1 }}>
            <div style={{ color: "var(--text-muted, #8a94a6)", marginBottom: 6, fontSize: 12 }}>
              Что сделано
            </div>
            {branch && (
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
                <GitBranch size={13} color="#8ec5ff" />
                <span className="break-anywhere">{branch}{head ? ` · ${head}` : ""}</span>
              </div>
            )}
            {cards.length > 0 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
                <FileText size={13} color="#e0cf9f" />
                <span>карточки: {cards.join(", ")}</span>
              </div>
            )}
            {prs.map((p) => (
              <div key={p} style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 3 }}>
                <GitPullRequest size={13} color="#c9a0ff" />
                <a href={p} target="_blank" rel="noreferrer" className="break-anywhere">{p.split("/").slice(-3).join("/")}</a>
              </div>
            ))}
            {files.length > 0 && (
              <div style={{ color: "var(--text-muted, #8a94a6)", fontSize: 12, marginTop: 4 }}>
                файлы: {files.join(", ")}
              </div>
            )}
          </div>
        )}

        <div style={{ minWidth: 200 }}>
          <div style={{ color: "var(--text-muted, #8a94a6)", marginBottom: 6, fontSize: 12 }}>
            Расход
          </div>
          {usage ? (
            <>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Coins size={13} color="#e0cf9f" />
                <strong>{num(usage.total_tokens)}</strong> токенов
              </div>
              <div style={{ color: "var(--text-muted, #8a94a6)", fontSize: 12, marginTop: 3 }}>
                выход {num(usage.output)} · чтение кэша {num(usage.cache_read)} · обращений {num(usage.messages)}
              </div>
              <div style={{ color: "var(--text-muted, #8a94a6)", fontSize: 12 }}>
                ≈ ${usage.cost_usd.toFixed(2)} по прайсу{usage.model ? ` · ${usage.model}` : ""}
              </div>
            </>
          ) : (
            <span style={{ color: "var(--text-muted, #8a94a6)", fontSize: 12 }}>считаю…</span>
          )}
        </div>
      </div>
    </section>
  );
}
