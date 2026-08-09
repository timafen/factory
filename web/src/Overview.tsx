import {
  Activity, CheckCircle2, Coins, HeartPulse,
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
    day_usd?: number; week_usd?: number; day_tokens?: number; week_tokens?: number;
    wasted_usd?: number; day_cost_defined?: boolean; week_cost_defined?: boolean;
    day_base_estimate?: boolean; week_base_estimate?: boolean;
    day_unknown_models?: string[]; week_unknown_models?: string[];
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
  limits?: Record<string, { state?: string; manual_off?: boolean; resets_at?: string; used_percent?: number }>;
  access?: Record<string, { enabled?: boolean } | boolean>;
  recent_done?: RecentDone[];
  health?: { merged_today?: number; merged_yesterday?: number;
             rounds_median?: number | null;
             review_first_pass?: [number, number] | null;
             minutes_median?: number | null };
  projects?: ProductProject[];
  janitor?: string;
};

export type ProductEnvironment = { name: string; status: "available" | "unavailable"; release_label?: string; health?: "healthy" | "unhealthy" };
export type ProductProject = { id: string; name: string; remote_identity: string; main_subject?: string; provider_status: "configured" | "not_configured"; environments: ProductEnvironment[] };

// eslint-disable-next-line react-refresh/only-export-components
export function productState(project: ProductProject) {
  if (project.provider_status !== "configured") return "Стенд не настроен";
  if (project.environments.some((environment) => environment.status !== "available")) return "Сведения о выпуске недоступны";
  return "Данные доступны";
}

type ActiveTask = {
  id: string;
  title: string;
  state: "queued" | "running" | string;
  created_at?: string;
};
type WorkMeta = { origin?: "owner" | "assistant" | "orchestrator" };
export type RecentDone = { title: string; detail?: string; at?: string };
type OverviewWork = {
  id: string;
  title: string;
  stage: string;
  origin: string;
  state: string;
};

const ORIGIN_RU: Record<string, string> = {
  owner: "поставил ты",
  assistant: "поставил Клод",
  orchestrator: "развернулось из эпика",
};

const MAX_TASK_PAGES = 500;

// eslint-disable-next-line react-refresh/only-export-components
export async function fetchAllTasks(): Promise<ActiveTask[]> {
  const tasks: ActiveTask[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_TASK_PAGES; page += 1) {
    const url = cursor
      ? `/api/v1/tasks?limit=200&cursor=${encodeURIComponent(cursor)}`
      : "/api/v1/tasks?limit=200";
    const response = await fetch(url);
    if (!response.ok) break;
    const body = (await response.json()) as { tasks?: ActiveTask[]; next_cursor?: string | null };
    tasks.push(...(body.tasks ?? []));
    if (!body.next_cursor) break;
    cursor = body.next_cursor;
  }
  return tasks;
}

// eslint-disable-next-line react-refresh/only-export-components
export function overviewWork(tasks: ActiveTask[], works: Record<string, WorkMeta>): OverviewWork[] {
  return tasks
    .filter((task) => task.state === "running" || task.state === "queued")
    .map((task) => {
      const match = /^\[auto\]\s*\[\d+\/\d+\s+([^\]]+)\]\s*(.*)$/.exec(task.title);
      const title = (match?.[2] || task.title.replace(/^\[auto\]\s*/, "")).trim();
      const origin = works[title]?.origin;
      return {
        id: task.id,
        title,
        stage: match?.[1]?.trim() || "Без этапа",
        origin: origin ? (ORIGIN_RU[origin] ?? origin) : "кто поставил — не указано",
        state: task.state,
      };
    })
    .sort((a, b) => Number(a.state === "queued") - Number(b.state === "queued"));
}

const card: React.CSSProperties = {
  background: "var(--surface, #171b24)", border: "1px solid var(--border, #262c38)",
  borderRadius: 12, padding: 16,
};
const muted = "var(--text-muted, #8a94a6)";

// eslint-disable-next-line react-refresh/only-export-components
export function cpuLoadExplanation(running: number, slots?: { busy: number; capacity: number }) {
  if (slots) {
    return `Причина загрузки процессора: активно работ ${running}; занято мест ${slots.busy} из ${slots.capacity}.`;
  }
  return `Причина загрузки процессора: активно работ ${running}. Данных о занятых местах нет.`;
}

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
  const [activeWork, setActiveWork] = useState<OverviewWork[]>([]);
  const [loading, setLoading] = useState(true);

  const pull = async () => {
    try {
      const [dashboardResponse, tasks, worksResponse] = await Promise.all([
        fetch("/api/v1/dashboard"), fetchAllTasks(), fetch("/api/v1/works"),
      ]);
      if (dashboardResponse.ok) setD((await dashboardResponse.json()) as Dash);
      if (worksResponse.ok) {
        const works = (await worksResponse.json()) as Record<string, WorkMeta>;
        setActiveWork(overviewWork(tasks, works));
      }
    } catch { /* тихо */ } finally { setLoading(false); }
  };
  useEffect(() => {
    // Initial fetch is the external synchronization performed by this effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
      ? { text: "Всё идёт — твоего участия не нужно", tone: "ok" as const, icon: <Activity size={22} /> }
      : queued > 0
        ? { text: "Работа в очереди, ждём исполнителя", tone: "muted" as const, icon: <Loader2 size={22} /> }
        : { text: "Фабрика свободна", tone: "muted" as const, icon: <CheckCircle2 size={22} /> };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Обзор</h1>
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
      </section>

      <section style={card} aria-labelledby="active-work-title">
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
          <Activity size={16} color="#8ec5ff" />
          <strong id="active-work-title">Сейчас в работе</strong>
          <span style={{ fontSize: 12, color: muted }}>{activeWork.length}</span>
        </div>
        {activeWork.length === 0 ? (
          <div style={{ fontSize: 13, color: muted }}>Активных работ нет.</div>
        ) : activeWork.map((work) => (
          <div
            key={work.id}
            onClick={() => onNav?.("work")}
            style={{ cursor: "pointer", marginTop: 8, padding: "10px 14px",
                     background: "#151b26", border: "1px solid #242e3f",
                     borderRadius: 10, display: "flex", flexDirection: "column", gap: 6 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <strong style={{ flex: 1, minWidth: 0, overflow: "hidden",
                               textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{work.title}</strong>
              <Pill text={work.state === "running" ? "выполняется" : "в очереди"}
                    tone={work.state === "running" ? "ok" : "muted"} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 12, color: muted, flex: 1 }}>{work.origin}</span>
              <span style={{ fontSize: 12, color: "#8ec5ff", whiteSpace: "nowrap" }}>этап: {work.stage}</span>
            </div>
          </div>
        ))}
      </section>

      {d.health && (
        <section style={card} aria-label="Здоровье конвейера">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Activity size={15} color="#8ec5ff" /><strong style={{ fontSize: 14 }}>Здоровье конвейера</strong>
            <span style={{ fontSize: 11.5, color: muted }}>по последним влитым работам</span>
          </div>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 19, fontWeight: 700 }}>{d.health.merged_today ?? 0}</div>
              <div style={{ fontSize: 11.5, color: muted }}>влито сегодня{typeof d.health.merged_yesterday === "number" ? " (вчера " + d.health.merged_yesterday + ")" : ""}</div>
            </div>
            {d.health.rounds_median != null && (
              <div>
                <div style={{ fontSize: 19, fontWeight: 700 }}>{d.health.rounds_median}</div>
                <div style={{ fontSize: 11.5, color: muted }}>кругов разработки на работу</div>
              </div>
            )}
            {d.health.review_first_pass && (
              <div>
                <div style={{ fontSize: 19, fontWeight: 700 }}>{d.health.review_first_pass[0]} из {d.health.review_first_pass[1]}</div>
                <div style={{ fontSize: 11.5, color: muted }}>прошли Ревью с первого раза</div>
              </div>
            )}
            {d.health.minutes_median != null && (
              <div>
                <div style={{ fontSize: 19, fontWeight: 700 }}>~{d.health.minutes_median} мин</div>
                <div style={{ fontSize: 11.5, color: muted }}>от старта до вливания</div>
              </div>
            )}
          </div>
        </section>
      )}

      {(d.recent_done ?? []).length > 0 && (
        <section style={card} aria-label="Сделано недавно">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <CheckCircle2 size={16} color="#7ee2a8" /><strong>Сделано недавно</strong>
          </div>
          {(d.recent_done ?? []).map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10,
                                  padding: "7px 0",
                                  borderTop: i ? "1px solid #1d2430" : "none" }}>
              <span style={{ color: "#7ee2a8", fontSize: 13, flex: "none" }}>✓</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap" }}>{r.title}</div>
                {r.detail && <div style={{ fontSize: 12, color: muted, overflow: "hidden",
                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.detail}</div>}
              </div>
              <span style={{ fontSize: 11.5, color: muted, flex: "none" }}>{(r.at || "").slice(5, 16)}</span>
            </div>
          ))}
        </section>
      )}

      {/* 2. Продукты: один честный блок на зарегистрированный проект */}
      {(d.projects ?? []).map((project) => <section style={card} key={project.id} aria-label={`Продукт — ${project.name}`}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <Server size={16} color="#8ec5ff" /><strong>Продукт — {project.name}</strong>
          <span style={{ flex: 1 }} /><span style={{ fontSize: 12, color: muted }}>последнее изменение: {project.main_subject || "недоступно"}</span>
        </div>
        {project.provider_status !== "configured" ? <div style={{ color: "#e0cf9f" }}>Стенд не настроен</div> :
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>{project.environments.map((environment)=><div key={environment.name} style={{ minWidth: 240, flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}><strong>{environment.name}</strong>{environment.status === "available" && <Pill text={environment.health === "healthy" ? "отвечает" : "не отвечает"} tone={environment.health === "healthy" ? "ok" : "bad"}/>}</div>
            {environment.status === "available" ? <div style={{ fontSize: 12.5, color: muted }}>релиз: {environment.release_label}</div> : <div style={{ color: "#e0cf9f" }}>Сведения о выпуске недоступны</div>}
          </div>)}</div>}
      </section>)}

      {/* 3. Расход и лимиты */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <section style={{ ...card, flex: 1, minWidth: 280 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <Coins size={16} color="#e0cf9f" /><strong>Расход</strong>
            <span style={{ fontSize: 11, color: muted }}>
              {d.spend?.day_base_estimate || d.spend?.week_base_estimate
                ? "базовая оценка по API-тарифу (журнал не сообщает запись кэша)"
                : "оценка по API-тарифу"} · Клод по задачам, Codex общим итогом
            </span>
          </div>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", fontSize: 13 }}>
            <div><div style={{ color: muted, fontSize: 12 }}>за сутки</div>
                 <strong style={{ fontSize: 18 }}>{d.spend?.day_cost_defined === false ? "стоимость не определена" : `$${(d.spend?.day_usd ?? 0).toFixed(2)}`}</strong>
                 {(d.spend?.day_tokens ?? 0) > 0 && <div style={{ color: muted, fontSize: 11 }}>{(d.spend?.day_tokens ?? 0).toLocaleString("ru-RU")} токенов Codex</div>}</div>
            <div><div style={{ color: muted, fontSize: 12 }}>за неделю</div>
                 <strong style={{ fontSize: 18 }}>{d.spend?.week_cost_defined === false ? "стоимость не определена" : `$${(d.spend?.week_usd ?? 0).toFixed(2)}`}</strong>
                 {(d.spend?.week_tokens ?? 0) > 0 && <div style={{ color: muted, fontSize: 11 }}>{(d.spend?.week_tokens ?? 0).toLocaleString("ru-RU")} токенов Codex</div>}</div>
            <div><div style={{ color: muted, fontSize: 12 }}>впустую за сутки</div>
                 <strong style={{ fontSize: 18, color: (d.spend?.wasted_usd ?? 0) > 0 ? "#e0cf9f" : undefined }}>
                   ${(d.spend?.wasted_usd ?? 0).toFixed(2)}</strong></div>
          </div>
          {d.spend?.worst && (
            <div style={{ marginTop: 10, fontSize: 12.5, color: muted }}>
              самая дорогая за сутки: ${d.spend.worst.usd} — {d.spend.worst.title}
            </div>
          )}
          {d.spend?.week_cost_defined === false && (
            <div style={{ marginTop: 10, fontSize: 12.5, color: "#e0cf9f" }}>
              Нет точного API-тарифа: {(d.spend.week_unknown_models ?? []).join(", ")}
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
                {h.cpu && (
                  <div style={{ fontSize: 12, color: muted, marginTop: 5 }}>
                    {cpuLoadExplanation(running, h.slots)}
                  </div>
                )}
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
                    прошлый ответ{last?.at ? " (" + last.at.slice(11, 16) + ")" : ""} дал запасной — основной тогда молчал
                    {b.chain[0] && !b.chain[0].blocked
                      ? "; сейчас основной снова доступен и вернётся со следующим вопросом"
                      : ""}
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
                {typeof l.used_percent === "number" && (
                  <span style={{ fontSize: 12.5, color: l.used_percent >= 80 ? "#e0b877" : muted }}
                        title="Остаток недельного лимита подписки — настоящий счётчик провайдера">
                    осталось {Math.max(0, Math.round(100 - l.used_percent))}%
                  </span>
                )}
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
