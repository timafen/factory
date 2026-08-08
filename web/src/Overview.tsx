import {
  Activity, AlertTriangle, CheckCircle2, Coins, GitBranch, HeartPulse,
  KeyRound, Loader2, MessageCircleQuestion, RefreshCw, Server, Users,
} from "lucide-react";
import { useEffect, useState } from "react";

type Dash = {
  updated_at?: string;
  now?: {
    running?: { id: string; title: string }[];
    running_count?: number;
    queued_count?: number;
    questions?: { id: string; title: string; question: string }[];
    questions_count?: number;
  };
  spend?: {
    day_usd?: number; week_usd?: number; wasted_usd?: number;
    worst?: { usd: number; title: string; id: string } | null;
  };
  workers?: Record<string, { total: number; healthy: number }>;
  host?: {
    state?: string;
    cpu?: { load1: number; cores: number; percent: number; state: string };
    memory?: { total_gb: number; available_gb: number; percent: number; state: string };
    disk?: { total_gb: number; free_gb: number; percent: number; state: string };
    slots?: { busy: number; capacity: number; percent: number; state: string };
  };
  brain?: {
    chain?: { cli: string; model: string; provider: string; note?: string; blocked?: boolean }[];
    last?: { cli?: string; model?: string; provider?: string; fallback?: boolean; at?: string };
  };
  limits?: Record<string, { state?: string; manual_off?: boolean; resets_at?: string }>;
  access?: Record<string, { enabled?: boolean } | boolean>;
  release?: {
    staging_release?: string; prod_release?: string;
    main_head?: string; main_subject?: string;
    staging_commit_known?: boolean; prod_commit_known?: boolean;
    staging_in_main?: boolean; prod_in_main?: boolean;
    staging_health?: string; prod_health?: string;
  };
  janitor?: string;
};

type WorkMetadata = Record<string, { origin?: "owner" | "assistant" | "orchestrator"; stage?: string }>;

const stageLabels: Record<string, string> = {
  Triage: "Разбор",
  Specification: "Спецификация",
  "Implement + Test": "Разработка и тесты",
  Review: "Ревью",
  Verify: "Проверка",
};

const originLabels: Record<string, string> = {
  owner: "поставил владелец",
  assistant: "поставила Фабрика (управляющий)",
  orchestrator: "поставила Фабрика (управляющий)",
};

function cleanActiveWorkTitle(title: string) {
  return title.replace(/^\[auto\]\s*/, "").replace(/^\[\d+\/\d+\s+[^\]]+\]\s*/, "").trim();
}

const card: React.CSSProperties = {
  background: "var(--surface, #171b24)", border: "1px solid var(--border, #262c38)",
  borderRadius: 12, padding: 16,
};
const muted = "var(--text-muted, #8a94a6)";

function Pill({ text, tone }: { text: string; tone: "ok" | "warn" | "bad" | "muted" }) {
  const c = { ok: ["#16341f", "#7ee2a8"], warn: ["#3a2f16", "#e0cf9f"],
              bad: ["#3b1d1d", "#ffb4b4"], muted: ["#22262f", "#8a94a6"] }[tone];
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 999,
                   background: c[0], color: c[1], whiteSpace: "nowrap" }}>{text}</span>
  );
}

/** Главный экран отвечает на один вопрос: всё ли идёт, и если нет — что мешает. */
export function Overview({ onNav }: { onNav?: (page: string) => void }) {
  const [d, setD] = useState<Dash>({});
  const [works, setWorks] = useState<WorkMetadata>({});
  const [worksUnavailable, setWorksUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);

  const pull = async () => {
    try {
      const [dashboardResult, worksResult] = await Promise.allSettled([
        fetch("/api/v1/dashboard"),
        fetch("/api/v1/works"),
      ]);
      if (dashboardResult.status === "fulfilled" && dashboardResult.value.ok) {
        setD((await dashboardResult.value.json()) as Dash);
      }
      if (worksResult.status === "fulfilled" && worksResult.value.ok) {
        setWorks((await worksResult.value.json()) as WorkMetadata);
        setWorksUnavailable(false);
      } else {
        setWorksUnavailable(true);
      }
    } catch { /* тихо */ } finally { setLoading(false); }
  };
  useEffect(() => {
    void pull();
    const h = window.setInterval(() => void pull(), 20000);
    return () => window.clearInterval(h);
  }, []);

  const q = d.now?.questions_count ?? 0;
  const running = d.now?.running_count ?? 0;
  const queued = d.now?.queued_count ?? 0;

  const headline = q > 0
    ? { text: `Ждёт твоего ответа: ${q}`, tone: "warn" as const, icon: <MessageCircleQuestion size={22} /> }
    : running > 0
      ? { text: "Всё идёт", tone: "ok" as const, icon: <Activity size={22} /> }
      : queued > 0
        ? { text: "Работа в очереди, ждём исполнителя", tone: "muted" as const, icon: <Loader2 size={22} /> }
        : { text: "Фабрика свободна", tone: "muted" as const, icon: <CheckCircle2 size={22} /> };

  const rel = d.release ?? {};
  const mainOk = rel.staging_in_main === true;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Главное</h1>
        <span style={{ fontSize: 12, color: muted }}>
          {d.updated_at ? `снимок ${new Date(d.updated_at).toLocaleTimeString("ru-RU")}` : ""}
        </span>
        <span style={{ flex: 1 }} />
        <button className="button" onClick={() => void pull()} title="Обновить">
          {loading ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
        </button>
      </div>

      {/* 1. Всё ли идёт */}
      <section
        style={{ ...card, borderColor: headline.tone === "warn" ? "#5a4a2a" : "var(--border, #262c38)",
                 cursor: q > 0 ? "pointer" : "default" }}
        onClick={() => { if (q > 0) onNav?.("answer"); }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ color: headline.tone === "warn" ? "#e0cf9f" : headline.tone === "ok" ? "#7ee2a8" : muted }}>
            {headline.icon}
          </span>
          <strong style={{ fontSize: 20 }}>{headline.text}</strong>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 13, color: muted }}>
            в работе {running} · в очереди {queued}
          </span>
        </div>
        {(d.now?.questions ?? []).length > 0 && (
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
            {(d.now?.questions ?? []).map((x) => (
              <div key={x.id} style={{ fontSize: 13, color: "#e0cf9f" }}>
                ❓ {x.title} — {x.question}
              </div>
            ))}
            <span style={{ fontSize: 12, color: muted }}>нажми, чтобы ответить ›</span>
          </div>
        )}
        <div role="region" aria-label="Сейчас в работе" style={{ marginTop: 10 }}>
          {(d.now?.running ?? []).length === 0 ? (
            <div style={{ fontSize: 13, color: muted }}>Сейчас активной работы нет.</div>
          ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {(d.now?.running ?? []).map((t) => (
              <div key={t.id} style={{ fontSize: 13, color: muted, cursor: "pointer" }}
                   onClick={(e) => { e.stopPropagation(); onNav?.("work"); }}>
                <strong style={{ color: "var(--text, #f2f4f8)" }}>▸ {cleanActiveWorkTitle(t.title) || "Работа без названия"}</strong>
                <div>{works[t.id]?.origin ? originLabels[works[t.id].origin!] : "постановщик не указан"}</div>
                <div>Этап: {works[t.id]?.stage ? stageLabels[works[t.id].stage!] ?? works[t.id].stage : "не указан"}</div>
              </div>
            ))}
          </div>
          )}
          {worksUnavailable && <div style={{ marginTop: 6, fontSize: 12, color: "#e0cf9f" }}>Данные о постановщике или этапе могут быть неполными.</div>}
        </div>
      </section>

      {/* 2. Продукт: что где живёт */}
      <section style={card}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Server size={16} color="#8ec5ff" /><strong>Продукт</strong>
          <span style={{ flex: 1 }} />
          {rel.main_head && <span style={{ fontSize: 12, color: muted }}>main: {rel.main_head}</span>}
        </div>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {([["Стейдж", rel.staging_release, rel.staging_health, rel.staging_in_main, rel.staging_commit_known],
             ["Прод", rel.prod_release, rel.prod_health, rel.prod_in_main, rel.prod_commit_known]] as const).map(
            ([name, release, health, inMain, known]) => (
              <div key={name} style={{ minWidth: 240, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <strong style={{ fontSize: 14 }}>{name}</strong>
                  <Pill text={/HTTP (2|3)\d\d/.test(health ?? "") ? "отвечает" : "не отвечает"}
                        tone={/HTTP (2|3)\d\d/.test(health ?? "") ? "ok" : "bad"} />
                </div>
                <div style={{ fontSize: 12.5, color: muted }}>релиз {release || "—"}</div>
                <div style={{ fontSize: 12.5, marginTop: 3 }}>
                  {known === false
                    ? <span style={{ color: "#ffb4b4" }}>коммита нет в репозитории</span>
                    : inMain
                      ? <span style={{ color: "#7ee2a8" }}>собран из main</span>
                      : <span style={{ color: "#e0cf9f" }}>не из main — расхождение</span>}
                </div>
              </div>
            ))}
        </div>
        {!mainOk && (
          <div style={{ marginTop: 10, fontSize: 12.5, color: "#e0cf9f" }}>
            <AlertTriangle size={13} style={{ verticalAlign: -2 }} /> Развёрнутое не собрано из main.
            Пока это так, выкат из главной ветки включать нельзя.
          </div>
        )}
        {rel.main_subject && (
          <div style={{ marginTop: 8, fontSize: 12, color: muted }}>
            <GitBranch size={12} style={{ verticalAlign: -2 }} /> последнее в main: {rel.main_subject}
          </div>
        )}
      </section>

      {/* 3. Расход и лимиты */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <section style={{ ...card, flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <Coins size={16} color="#e0cf9f" /><strong>Расход</strong>
            <span style={{ fontSize: 11, color: muted }}>по прайсу API, справочно</span>
          </div>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", fontSize: 13 }}>
            <div><div style={{ color: muted, fontSize: 12 }}>за сутки</div>
                 <strong style={{ fontSize: 18 }}>${(d.spend?.day_usd ?? 0).toFixed(2)}</strong></div>
            <div><div style={{ color: muted, fontSize: 12 }}>за неделю</div>
                 <strong style={{ fontSize: 18 }}>${(d.spend?.week_usd ?? 0).toFixed(2)}</strong></div>
            <div><div style={{ color: muted, fontSize: 12 }}>впустую за сутки</div>
                 <strong style={{ fontSize: 18, color: (d.spend?.wasted_usd ?? 0) > 0 ? "#e0cf9f" : undefined }}>
                   ${(d.spend?.wasted_usd ?? 0).toFixed(2)}</strong></div>
          </div>
          {d.spend?.worst && (
            <div style={{ marginTop: 10, fontSize: 12.5, color: muted }}>
              самая дорогая за сутки: ${d.spend.worst.usd} — {d.spend.worst.title}
            </div>
          )}
        </section>

        <section style={{ ...card, flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <HeartPulse size={16} color="#7ee2a8" /><strong>Нагрузка сервера</strong>
          </div>
          {(() => {
            const h = d.host;
            if (!h) return <div style={{ opacity: 0.6 }}>нет данных</div>;
            const colour = (st?: string) =>
              st === "over" ? "#ff9d9d" : st === "tight" ? "#e0cf9f" : "#7ee2a8";
            const verdict = h.state === "over" ? "перегружен — новую работу не беру"
              : h.state === "tight" ? "плотно, но справляется"
              : "есть запас";
            const bar = (label: string, pct: number, st: string | undefined, detail: string) => (
              <div key={label} style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span>{label}</span>
                  <span style={{ color: colour(st) }}>{pct}% · {detail}</span>
                </div>
                <div style={{ height: 5, borderRadius: 3, background: "#232833", marginTop: 3 }}>
                  <div style={{ height: 5, borderRadius: 3, width: Math.min(100, pct) + "%",
                                background: colour(st) }} />
                </div>
              </div>
            );
            return (
              <>
                <div style={{ fontSize: 15, marginBottom: 10, color: colour(h.state) }}>
                  {verdict}
                </div>
                {h.cpu && bar("Процессор", h.cpu.percent, h.cpu.state,
                              h.cpu.load1 + " из " + h.cpu.cores + " ядер")}
                {h.memory && bar("Память", h.memory.percent, h.memory.state,
                                 "свободно " + h.memory.available_gb + " ГБ")}
                {h.disk && bar("Диск", h.disk.percent, h.disk.state,
                               "свободно " + h.disk.free_gb + " ГБ")}
                {h.slots && bar("Занято мест", h.slots.percent, h.slots.state,
                                h.slots.busy + " из " + h.slots.capacity)}
              </>
            );
          })()}
        </section>

        <section style={{ ...card, flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <HeartPulse size={16} color="#c3aef0" /><strong>Чем думает Фабрика</strong>
          </div>
          {(() => {
            const b = d.brain;
            if (!b?.chain?.length) return <div style={{ opacity: 0.6 }}>нет данных</div>;
            const last = b.last;
            const now = last?.model
              ? b.chain.find((e) => e.model === last.model)
              : b.chain.find((e) => !e.blocked);
            return (
              <>
                <div style={{ fontSize: 15, marginBottom: 2 }}>
                  {now ? now.model + " · " + now.provider : "все движки недоступны"}
                </div>
                {last?.fallback && (
                  <div style={{ fontSize: 12.5, color: "#e0cf9f", marginBottom: 6 }}>
                    работает запасной: основной не ответил
                  </div>
                )}
                <div style={{ fontSize: 12.5, opacity: 0.6, margin: "6px 0 4px" }}>
                  Порядок замены, если основной недоступен:
                </div>
                {b.chain.map((e, i) => (
                  <div key={e.model} style={{
                    display: "flex", gap: 8, alignItems: "baseline", fontSize: 13,
                    opacity: e.blocked ? 0.45 : 1,
                  }}>
                    <span style={{ opacity: 0.6, minWidth: 14 }}>{i + 1}.</span>
                    <span style={{ color: now && e.model === now.model ? "#c3aef0" : undefined }}>
                      {e.model}
                    </span>
                    {e.blocked && <span style={{ opacity: 0.6, fontSize: 12 }}>· недоступен</span>}
                  </div>
                ))}
              </>
            );
          })()}
        </section>

        <section style={{ ...card, flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <HeartPulse size={16} color="#7ee2a8" /><strong>Подписки и исполнители</strong>
          </div>
          {["claude", "codex"].map((p) => {
            const l = d.limits?.[p] ?? {};
            const wk = d.workers?.[p];
            const off = !!l.manual_off;
            const blocked = l.state === "exhausted" || l.state === "throttled";
            return (
              <div key={p} style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0", flexWrap: "wrap" }}>
                <span style={{ minWidth: 66, fontWeight: 600, fontSize: 13 }}>
                  {p === "claude" ? "Claude" : "Codex"}
                </span>
                <Pill text={off ? "выключен" : blocked ? "лимит" : "свободна"}
                      tone={off || blocked ? "bad" : "ok"} />
                <span style={{ fontSize: 12.5, color: muted }}>
                  <Users size={12} style={{ verticalAlign: -2 }} />{" "}
                  {wk ? `${wk.healthy} здоровых из ${wk.total}` : "нет исполнителей"}
                </span>
              </div>
            );
          })}
          <div style={{ marginTop: 8, fontSize: 12, color: muted }}>
            <KeyRound size={12} style={{ verticalAlign: -2 }} /> открыто:{" "}
            {Object.entries(d.access ?? {})
              .filter(([, v]) => (typeof v === "object" ? v?.enabled : v))
              .map(([k]) => k).join(", ") || "ничего"}
          </div>
        </section>
      </div>

      {d.janitor && (
        <div style={{ fontSize: 12, color: muted }}>
          санитар воркеров: {d.janitor}
        </div>
      )}
    </div>
  );
}
