import {
  Activity, BarChart3, CheckCircle2, Coins, HeartPulse,
  KeyRound, Loader2, MessageCircleQuestion, RefreshCw, Server, Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { stageHandoffTargetStatus } from "./efficiency";

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
  recent_done?: RecentDoneSnapshot | RecentDone[];
  projects?: ProductProject[];
  janitor?: string;
  release_train?: ReleaseTrainSnapshot | null;
};

type ReleasePassenger = { title: string };
type ReleaseTrain = {
  target: string; state: "idle" | "waiting" | "running" | "succeeded" | "failed";
  generation?: number; gate?: string; started_at?: string; elapsed_seconds?: number;
  passengers: ReleasePassenger[];
  next: { requested: boolean; passengers: ReleasePassenger[]; retry_at?: string };
  previous?: { state: "succeeded" | "failed"; finished_at?: string; passengers: ReleasePassenger[] };
};
type ReleaseTrainSnapshot = { updated_at: string; trains: ReleaseTrain[] };

type EfficiencyDistribution = { sample: number; median: number | null; p90: number | null };
type EfficiencyRate = { count: number; total: number; rate: number | null };
type EfficiencyTimeShare = { key: string; definition: string; sample: number; seconds: number; denominator_seconds: number; share: number | null };
type EfficiencyTarget = { maximum_share: number; current_share: number | null; previous_share: number | null; met: boolean | null };
type EfficiencyPeriod = {
  started_at: string; ended_at: string; completed_works: number; product_stage_tasks: number;
  lead_time_seconds: EfficiencyDistribution; time_shares: EfficiencyTimeShare[];
  unclassified_too_high: boolean; unclassified_threshold: number;
  review_first_pass: EfficiencyRate; verify_first_pass: EfficiencyRate;
  rounds: EfficiencyDistribution; final_dead_ends: EfficiencyRate;
  automatic_recoveries: number; release_failures: number; rollbacks: number;
  excluded: { patrol: number; scheduled: number; helper: number; other: number; total: number };
};
type EfficiencyComparison = { assessment: "low_data" | "degraded" | "mixed" | "improved" | "stable"; stage_handoff_wait_target?: EfficiencyTarget; current: EfficiencyPeriod; previous: EfficiencyPeriod };
type EfficiencySummary = { generated_at: string; minimum_sample: number; release_observation_started_at?: string; periods: Record<"24h" | "7d", EfficiencyComparison> };
type ProductCapacityPeriod = {
  started_at: string; ended_at: string; observation_from?: string; samples: number; low_data: boolean;
  active_time: { active: number; seconds: number; share: number | null }[];
  average_busy: number | null; queue_p90: number | null;
  underload: { reason: string; seconds: number; share: number | null }[] | null;
};
type ProductCapacitySummary = { generated_at: string; capacity: number; periods: Record<"24h" | "7d", ProductCapacityPeriod> };
type QueueMetrics = { queue_reassignments?: number };

export type ProductEnvironment = { name: string; status: "available" | "unavailable"; release_label?: string; health?: "healthy" | "unhealthy" };
export type ProjectReadinessState = "ready" | "needs_configuration" | "blocked" | "unknown";
export type ProjectReadinessVerdict = "ready" | "needs_configuration" | "blocked";
export type ProjectReadinessCheck = { key: string; title: string; state: ProjectReadinessState; reason: string };
export type ProjectReadiness = { verdict?: string; checked_at?: string; checks?: ProjectReadinessCheck[] };
export type ProductProject = { id: string; name: string; remote_identity: string; main_subject?: string; provider_status: "configured" | "not_configured"; environments: ProductEnvironment[]; readiness?: ProjectReadiness };

const READINESS_CATALOG = [
  ["repository", "Репозиторий"], ["workers", "Исполнители"],
  ["safe_environment", "Безопасный стенд"], ["access", "Доступы"],
  ["tests", "Тесты"], ["release", "Выпуск"], ["rollback", "Откат"],
  ["secrets", "Секреты"], ["browser", "Браузерный доступ"],
] as const;
const READINESS_STATES = new Set<ProjectReadinessState>(["ready", "needs_configuration", "blocked", "unknown"]);

// eslint-disable-next-line react-refresh/only-export-components
export function normalizeProjectReadiness(readiness?: ProjectReadiness) {
  const checks = READINESS_CATALOG.map(([key, title]) => {
    const source = readiness?.checks?.find((check) => check.key === key);
    const state = source && READINESS_STATES.has(source.state) ? source.state : "unknown";
    return {
      key, title, state,
      reason: source?.reason?.trim() || "Нет проверяемых данных.",
    } satisfies ProjectReadinessCheck;
  });
  const verdict: ProjectReadinessVerdict = checks.some((check) => check.state === "blocked")
    ? "blocked"
    : checks.every((check) => check.state === "ready") ? "ready" : "needs_configuration";
  return { verdict, checked_at: readiness?.checked_at, checks };
}

// eslint-disable-next-line react-refresh/only-export-components
export function productState(project: ProductProject) {
  if (project.provider_status !== "configured") return "Стенд не настроен";
  if (project.environments.some((environment) => environment.status !== "available")) return "Сведения о выпуске недоступны";
  return "Данные доступны";
}

function ReleaseTrainPanel({ snapshot }: { snapshot?: ReleaseTrainSnapshot | null }) {
  const trains = snapshot?.trains;
  const stateText = (state: ReleaseTrain["state"]) => ({
    idle: "свободен", waiting: "ожидает выпуска", running: "выполняется",
    succeeded: "успешно выпущен", failed: "выпуск не прошёл",
  })[state];
  const duration = (seconds?: number) => seconds == null
    ? "длительность неизвестна"
    : `идёт ${Math.floor(seconds / 60)} мин`;
  return <section style={card} aria-label="Поезд выпуска">
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <Server size={16} color="#8ec5ff" /><strong>Поезд выпуска</strong>
    </div>
    {!Array.isArray(trains) || trains.length === 0 ? (
      <div style={{ fontSize: 13, color: muted }}>Сведения о выпуске недоступны.</div>
    ) : [...trains].sort((a, b) => a.target.localeCompare(b.target)).map((train) => (
      <article key={train.target} style={{ padding: "10px 0", borderTop: "1px solid #1d2430" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <strong>{train.target}</strong><span>{stateText(train.state)}</span>
          {train.generation != null && <span style={{ color: muted }}>состав № {train.generation}</span>}
        </div>
        {train.gate && <div style={{ fontSize: 13, color: muted }}>Шаг: {train.gate}</div>}
        {(train.state === "waiting" || train.state === "running") &&
          <div style={{ fontSize: 13, color: muted }}>{duration(train.elapsed_seconds)}</div>}
        {train.passengers.length > 0 && <div style={{ fontSize: 13 }}>Едет: {train.passengers.map((p) => p.title).join(" · ")}</div>}
        {train.previous && <div style={{ fontSize: 13 }}>
          Прошлый состав: {train.previous.state === "succeeded" ? "успешно" : "ошибка"}
          {train.previous.finished_at ? ` · ${formatRecentDate(train.previous.finished_at)}` : " · время неизвестно"}
          {train.previous.passengers.length > 0 ? ` · ${train.previous.passengers.map((p) => p.title).join(" · ")}` : ""}
        </div>}
        {train.next.retry_at && <div style={{ fontSize: 13 }}>Следующая попытка: {formatRecentDate(train.next.retry_at)}</div>}
        {train.next.requested && <div style={{ fontSize: 13 }}>
          Следующий состав сядет в ближайший выпуск после текущего
          {train.next.passengers.length > 0 ? `: ${train.next.passengers.map((p) => p.title).join(" · ")}` : "."}
        </div>}
      </article>
    ))}
  </section>;
}

type ActiveTask = {
  id: string;
  title: string;
  state: "queued" | "running" | string;
  created_at?: string;
};
type WorkMeta = { origin?: string };
export type RecentDone = {
  title: string; detail?: string; at?: string;
  status?: "merged" | "failed";
};
export type RecentDoneSnapshot = { merged?: RecentDone[]; failed?: RecentDone[] };

// eslint-disable-next-line react-refresh/only-export-components
export function formatRecentDate(value: string | undefined, now = new Date()): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(value)) return "дата неизвестна";
  const parts = value.slice(0, 10).split("-").map(Number);
  const check = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
  if (check.getUTCFullYear() !== parts[0] || check.getUTCMonth() !== parts[1] - 1 || check.getUTCDate() !== parts[2]) return "дата неизвестна";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "дата неизвестна";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const delta = Math.round((today.getTime() - day.getTime()) / 86400000);
  const time = date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (delta === 0) return `сегодня ${time}`;
  if (delta === 1) return `вчера ${time}`;
  return `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()} ${time}`;
}
type OverviewWork = {
  id: string;
  title: string;
  stage: string;
  origin: string;
  state: string;
};

const ORIGIN_RU: Record<string, string> = {
  owner: "поставил ты",
  assistant: "поставил помощник",
  orchestrator: "запустила Factory",
  worker: "поставила Factory по находке",
  agent: "поставила Factory по находке",
  patrol: "поставил патруль",
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

const READINESS_LABELS = {
  ready: "Готово", needs_configuration: "Нужна настройка", blocked: "Заблокировано", unknown: "Неизвестно",
} satisfies Record<ProjectReadinessState, string>;
const READINESS_VERDICTS = {
  ready: "Готов", needs_configuration: "Требует настройки", blocked: "Заблокирован",
} satisfies Record<ProjectReadinessVerdict, string>;

function ProjectReadinessCard({ readiness }: { readiness?: ProjectReadiness }) {
  const normalized = normalizeProjectReadiness(readiness);
  const verdictTone = normalized.verdict === "ready" ? "ok" : normalized.verdict === "blocked" ? "bad" : "warn";
  return <div aria-label="Готовность проекта" style={{ marginTop: 14, borderTop: "1px solid #262c38", paddingTop: 12 }}>
    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
      <CheckCircle2 size={15} color="#8ec5ff" /><strong>Готовность проекта</strong>
      <Pill text={READINESS_VERDICTS[normalized.verdict]} tone={verdictTone} />
      <span style={{ flex: 1 }} />
      <span style={{ fontSize: 11.5, color: muted }}>снимок: {normalized.checked_at?.slice(0, 16).replace("T", " ") || "время неизвестно"}</span>
    </div>
    <div style={{ display: "grid", gap: 6 }}>
      {normalized.checks.map((check) => <div key={check.key} style={{ display: "grid", gridTemplateColumns: "minmax(145px, 0.7fr) minmax(125px, auto) minmax(220px, 1.7fr)", gap: 10, alignItems: "baseline", fontSize: 12.5 }}>
        <strong>{check.title}</strong>
        <span style={{ color: check.state === "ready" ? "#7ee2a8" : check.state === "blocked" ? "#ffb4b4" : "#e0cf9f" }}>{READINESS_LABELS[check.state]}</span>
        <span style={{ color: muted }}>{check.reason}</span>
      </div>)}
    </div>
  </div>;
}

const SHARE_RU: Record<string, string> = {
  queue: "В очереди", Triage: "Разбор", Specification: "Спецификация",
  "Implement + Test": "Разработка", Review: "Ревью", Verify: "Проверка",
  stage_handoff_wait: "Ожидание между стадиями",
  owner_decision_wait: "Ожидание решения владельца",
  merge_release_wait: "Ожидание слияния/выпуска",
  unclassified: "Unclassified",
};

function formatDuration(seconds: number | null) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} сек`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} мин`;
  const hours = seconds / 3600;
  if (hours < 48) return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)} ч`;
  return `${(hours / 24).toFixed(1)} д`;
}

function formatSeconds(seconds: number) {
  return Math.round(seconds).toLocaleString("ru-RU");
}

function formatRate(rate: EfficiencyRate) {
  return rate.total ? `${rate.count} из ${rate.total} (${Math.round((rate.rate ?? 0) * 100)}%)` : "— (n=0)";
}

function assessmentView(assessment: EfficiencyComparison["assessment"]) {
  if (assessment === "low_data") return { text: "данных мало", tone: "muted" as const };
  if (assessment === "degraded") return { text: "есть деградация", tone: "bad" as const };
  if (assessment === "mixed") return { text: "изменения разнонаправленные", tone: "warn" as const };
  if (assessment === "improved") return { text: "есть улучшение", tone: "ok" as const };
  return { text: "без явного изменения", tone: "muted" as const };
}

function EfficiencyPanel({ summary }: { summary: EfficiencySummary }) {
  const [window, setWindow] = useState<"24h" | "7d">("24h");
  const comparison = summary.periods[window];
  if (!comparison) return null;
  const current = comparison.current;
  const previous = comparison.previous;
  const previousShares = new Map(previous.time_shares.map((share) => [share.key, share]));
  const unclassified = current.time_shares.find((share) => share.key === "unclassified");
  const assessment = assessmentView(comparison.assessment);
  const handoffTarget = comparison.stage_handoff_wait_target;
  const handoffTargetStatus = handoffTarget
    ? stageHandoffTargetStatus(current.completed_works, summary.minimum_sample, handoffTarget.met)
    : null;
  const previousDates = `${formatRecentDate(previous.started_at)}–${formatRecentDate(previous.ended_at)}`;
  return (
    <section style={card} aria-label="Эффективность Factory">
      <div className="efficiency-heading">
        <div>
          <div className="efficiency-title"><BarChart3 size={16} color="#8ec5ff" /><strong>Эффективность Factory</strong></div>
          <div className="efficiency-subtitle">Только продуктовые работы, дошедшие до фактического слияния</div>
        </div>
        <div className="window-picker" aria-label="Период эффективности">
          <button type="button" aria-pressed={window === "24h"} onClick={() => setWindow("24h")}>24 часа</button>
          <button type="button" aria-pressed={window === "7d"} onClick={() => setWindow("7d")}>7 дней</button>
        </div>
      </div>

      <div className="efficiency-verdict">
        <Pill text={assessment.text} tone={assessment.tone} />
        <span>выборка: {current.completed_works} влитых работ · минимум для оценки {summary.minimum_sample}</span>
      </div>

      {window === "7d" && handoffTarget && <div className="efficiency-verdict" aria-label="Цель ожидания между стадиями">
        <Pill text={handoffTargetStatus!.text} tone={handoffTargetStatus!.tone} />
        <span>Ожидание между стадиями: цель ≤{Math.round(handoffTarget.maximum_share * 100)}% · текущие 7 дней {handoffTarget.current_share == null ? "—" : `${Math.round(handoffTarget.current_share * 100)}%`} · предыдущие 7 дней {handoffTarget.previous_share == null ? "—" : `${Math.round(handoffTarget.previous_share * 100)}%`}</span>
      </div>}

      {current.unclassified_too_high && <div className="efficiency-alert" role="alert">
        Красный сигнал: unclassified {Math.round((unclassified?.share ?? 0) * 100)}% превышает порог {Math.round(current.unclassified_threshold * 100)}%. Временных меток недостаточно для честной диагностики.
      </div>}

      <div className="efficiency-primary">
        <div><strong>{current.completed_works}</strong><span>влито</span><small>предыдущий период: {previous.completed_works}</small></div>
        <div><strong>{formatDuration(current.lead_time_seconds.median)}</strong><span>медиана до слияния</span><small>{current.lead_time_seconds.p90 == null ? "данных нет" : `90% влитых работ дошли до слияния не дольше чем за ${formatDuration(current.lead_time_seconds.p90)}`} · n={current.lead_time_seconds.sample}<br />ранее: медиана {formatDuration(previous.lead_time_seconds.median)} · {previous.lead_time_seconds.p90 == null ? "данных нет" : `90% — не дольше чем за ${formatDuration(previous.lead_time_seconds.p90)}`} · n={previous.lead_time_seconds.sample}</small></div>
        <div><strong>{formatRate(current.final_dead_ends)}</strong><span>окончательные тупики</span><small>ранее {formatRate(previous.final_dead_ends)}<br />знаменатель: слияния + тупики</small></div>
      </div>

      <details className="efficiency-details">
        <summary>Показать детали и знаменатели</summary>
        <div className="efficiency-detail-grid">
          <div>
            <h3>Качество прохождения</h3>
            <dl className="efficiency-facts">
              <div><dt>Review с первого раза</dt><dd>{formatRate(current.review_first_pass)}<br /><small>ранее {formatRate(previous.review_first_pass)}</small></dd></div>
              <div><dt>Verify с первого раза</dt><dd>{formatRate(current.verify_first_pass)}<br /><small>ранее {formatRate(previous.verify_first_pass)}</small></dd></div>
              <div><dt>Круги</dt><dd>медиана {current.rounds.median ?? "—"} · {current.rounds.p90 == null ? "данных нет" : `90% влитых работ прошли не больше ${current.rounds.p90} кругов`} · n={current.rounds.sample}<br /><small>ранее: медиана {previous.rounds.median ?? "—"} · {previous.rounds.p90 == null ? "данных нет" : `90% — не больше ${previous.rounds.p90} кругов`} · n={previous.rounds.sample}</small></dd></div>
              <div><dt>Автовосстановления</dt><dd>{current.automatic_recoveries} (ранее {previous.automatic_recoveries})</dd></div>
              <div><dt>Неуспешные выпуски / откаты</dt><dd>{current.release_failures} / {current.rollbacks}<br /><small>ранее {previous.release_failures} / {previous.rollbacks}</small></dd></div>
            </dl>
          </div>
          <div>
            <h3>Куда ушло время до слияния</h3>
            <div className="efficiency-shares">
              {current.time_shares.map((share) => <div key={share.key}>
                <span><b>{SHARE_RU[share.key] ?? share.key}</b><small>{share.definition}</small></span>
                <div><i style={{ width: `${Math.round((share.share ?? 0) * 100)}%` }} /></div>
                <strong>{formatSeconds(share.seconds)} сек · {share.share == null ? "—" : `${Math.round(share.share * 100)}%`}<small>n={share.sample} интервалов<br />ранее {formatSeconds(previousShares.get(share.key)?.seconds ?? 0)} сек · {previousShares.get(share.key)?.share == null ? "—" : `${Math.round((previousShares.get(share.key)?.share ?? 0) * 100)}%`} · n={previousShares.get(share.key)?.sample ?? 0}</small></strong>
              </div>)}
            </div>
          </div>
        </div>
        <div className="efficiency-sources">
          <strong>Что вошло:</strong> {current.product_stage_tasks} завершённых продуктовых этапов (ранее {previous.product_stage_tasks}). Служебные отдельно: патруль {current.excluded.patrol}, по расписанию {current.excluded.scheduled}, helper {current.excluded.helper}, прочие {current.excluded.other} (всего {current.excluded.total}; ранее {previous.excluded.total}).
          <br />Throughput считается по записям успешного слияния, не по состоянию «агент закончил». Доли времени имеют один знаменатель: {formatSeconds(current.time_shares[0]?.denominator_seconds ?? 0)} секунд от создания первой стадии до слияния по {current.completed_works} работам. Категории получают время только при наличии указанных временных меток; остаток остаётся unclassified. Порог красного сигнала — строго больше {Math.round(current.unclassified_threshold * 100)}%. Предыдущий сопоставимый период: {previousDates}.
          <br />First-pass считается только среди влитых работ, которые дошли до соответствующей проверки. Круг — наибольшее число повторов Разработки, Ревью или Проверки; автовосстановление — повтор того же этапа после ошибки или отмены. Окончательный тупик — работа без слияния и живого продолжения, которая не менялась хотя бы 10 минут.{summary.release_observation_started_at ? ` Журнал неуспешных выпусков ведётся с ${formatRecentDate(summary.release_observation_started_at)}; более ранние инциденты в число не входят.` : " Период наблюдения выпусков неизвестен — нули по выпускам нельзя считать подтверждённым отсутствием инцидентов."}
        </div>
      </details>
    </section>
  );
}

const UNDERLOAD_RU: Record<string, string> = {
  no_ready_work: "нет готовых работ", owner_question: "вопрос владельцу",
  provider_limit: "лимит провайдера", repository_conflict: "конфликт области или репозитория",
  release_lock: "блокировка выпуска", unknown: "unknown",
};

function ProductCapacityPanel({ summary }: { summary: ProductCapacitySummary }) {
  const [window, setWindow] = useState<"24h" | "7d">("24h");
  const period = summary.periods[window];
  if (!period) return null;
  const percentage = (value: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;
  return <section style={card} aria-label="Загрузка четырёх потоков">
    <div className="efficiency-heading">
      <div><div className="efficiency-title"><Users size={16} color="#8ec5ff" /><strong>Загрузка {summary.capacity} потоков</strong></div>
        <div className="efficiency-subtitle">Только product works; patrol, scheduled и helper исключены</div></div>
      <div className="window-picker" aria-label="Период загрузки">
        <button type="button" aria-pressed={window === "24h"} onClick={() => setWindow("24h")}>24 часа</button>
        <button type="button" aria-pressed={window === "7d"} onClick={() => setWindow("7d")}>7 дней</button>
      </div>
    </div>
    {period.low_data && <div className="efficiency-verdict"><Pill text="данных мало" tone="muted" /><span>наблюдение началось {period.observation_from ? formatRecentDate(period.observation_from) : "сейчас"}; историю не восстанавливали.</span></div>}
    <div className="efficiency-primary">
      <div><strong>{period.average_busy == null ? "—" : `${period.average_busy.toFixed(1)} / ${summary.capacity}`}</strong><span>средняя занятость</span><small>сэмплов: {period.samples}</small></div>
      <div><strong>{period.queue_p90 == null ? "—" : period.queue_p90}</strong><span>обычная длина очереди</span><small>{period.queue_p90 == null ? "данных нет" : `очередь обычно не длиннее ${period.queue_p90} продуктовых работ`}</small></div>
      <div><strong>{period.active_time.map((item) => `${item.active}: ${percentage(item.share)}`).join(" · ")}</strong><span>доля времени 0–4</span><small>в каждом числе — активных работ : доля</small></div>
    </div>
    <details className="efficiency-details"><summary>Показать причины недозагрузки</summary>
      <div className="efficiency-sources">{(period.underload ?? []).map((item) => <div key={item.reason}>{UNDERLOAD_RU[item.reason] ?? item.reason}: <strong>{percentage(item.share)}</strong></div>)}
        <br />Причина показывается только по наблюдаемому факту. Если очередь есть, а подтверждения причины нет, это <strong>unknown</strong>; нули не означают, что причина исключена.</div>
    </details>
  </section>;
}

/** Главный экран отвечает на один вопрос: всё ли идёт, и если нет — что мешает. */
export function Overview({ onNav }: { onNav?: (page: string) => void }) {
  const [d, setD] = useState<Dash>({});
  const [activeWork, setActiveWork] = useState<OverviewWork[]>([]);
  const [efficiency, setEfficiency] = useState<EfficiencySummary>();
  const [capacity, setCapacity] = useState<ProductCapacitySummary>();
  const [queueMetrics, setQueueMetrics] = useState<QueueMetrics>({});
  const [loading, setLoading] = useState(true);

  const pull = async () => {
    try {
      const [dashboardResponse, tasks, worksResponse, efficiencyResponse, capacityResponse, queueResponse] = await Promise.all([
        fetch("/api/v1/dashboard"), fetchAllTasks(), fetch("/api/v1/works"),
        fetch("/api/v1/metrics/efficiency"),
        fetch("/api/v1/metrics/product-capacity"),
        fetch("/api/v1/metrics/summary?window=24h"),
      ]);
      if (dashboardResponse.ok) setD((await dashboardResponse.json()) as Dash);
      if (efficiencyResponse.ok) {
        const value = (await efficiencyResponse.json()) as EfficiencySummary;
        if (value.periods?.["24h"] && value.periods?.["7d"]) setEfficiency(value);
      }
      if (capacityResponse.ok) {
        const value = (await capacityResponse.json()) as ProductCapacitySummary;
        if (value.periods?.["24h"] && value.periods?.["7d"]) setCapacity(value);
      }
      if (queueResponse.ok) setQueueMetrics((await queueResponse.json()) as QueueMetrics);
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

  const recent = Array.isArray(d.recent_done) ? { merged: [], failed: [] } : (d.recent_done ?? {});
  const merged = recent.merged ?? [];
  const failed = recent.failed ?? [];
  const recentGroups: { heading: string; items: RecentDone[]; kind: "merged" | "failed" }[] = [
    { heading: "Влито в main", items: merged, kind: "merged" },
    { heading: "Провалы", items: failed, kind: "failed" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 22 }}>Обзор</h1>
        <span style={{ fontSize: 12, color: muted }}>
          {d.updated_at ? `снимок ${formatRecentDate(d.updated_at)}` : ""}
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
            в работе {running} · в очереди {queued} · переназначено за 24 ч {queueMetrics.queue_reassignments ?? 0}
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

      <ReleaseTrainPanel snapshot={d.release_train} />

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

      {efficiency && <EfficiencyPanel summary={efficiency} />}
      {capacity && <ProductCapacityPanel summary={capacity} />}

      {(merged.length + failed.length) > 0 && (
        <section style={card} aria-label="Сделано недавно">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <CheckCircle2 size={16} color="#7ee2a8" /><strong>Сделано недавно</strong>
          </div>
          {recentGroups.map(({ heading, items, kind }) => items.length > 0 && <div key={heading}>
            <strong style={{ fontSize: 12, color: muted }}>{heading}</strong>
            {items.map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10,
                                  padding: "7px 0",
                                  borderTop: i ? "1px solid #1d2430" : "none" }}>
              <span style={{ color: kind === "failed" ? "#ff9d9d" : "#7ee2a8", fontSize: 13, flex: "none" }}>
                {kind === "failed" ? "!" : "✓"}
              </span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13.5, overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap" }}>{r.title}</div>
                {r.detail && <div style={{ fontSize: 12, color: muted, overflow: "hidden",
                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.detail}</div>}
              </div>
              <span style={{ fontSize: 11.5, color: muted, flex: "none" }}>{formatRecentDate(r.at)}</span>
            </div>
            ))}
          </div>)}
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
        <ProjectReadinessCard readiness={project.readiness} />
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
