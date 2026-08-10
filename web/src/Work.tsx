import { ChevronRight, LayoutGrid, ListChecks, Plus, Rows3 } from "lucide-react";
import { useEffect, useState } from "react";
import { runtimeLabel, taskStates, timeAgo } from "./format";
import { ProjectTag, useProjectName } from "./project";
import type { Task, TaskState, Worker } from "./types";
import {
  EmptyState, ErrorState, LoadingState, StaleBanner, ViewHeader, type ViewStateProps,
} from "./ui";

const STAGE_ORDER = ["Triage", "Specification", "Implement + Test", "Review", "Verify"];
const STAGE_RU: Record<string, string> = {
  "Triage": "Разбор", "Specification": "Спецификация", "Implement + Test": "Разработка",
  "Review": "Ревью", "Verify": "Проверка",
};

type Verdict = { action?: string; final_pass?: boolean; stage?: string;
                 // Где владельцу открыть сделанное и посмотреть.
                 try_url?: string; proof?: string;
};
type Question = { task_id?: string; status?: string; question?: string };
type HistoryEntry = { task_id: string; text: string };
type WorkMeta = {
  origin?: "owner" | "assistant" | "orchestrator";
  start_stage?: string;
  skipped?: string[];
  reason?: string;
  closed?: string;
  closed_reason?: string;
};
const ORIGIN_RU: Record<string, string> = {
  owner: "поставил ты",
  assistant: "поставил Клод",
  orchestrator: "развернулось из эпика",
};

const TONE: Record<string, { bg: string; fg: string }> = {
  ok:    { bg: "#16341f", fg: "#7ee2a8" },
  warn:  { bg: "#3a2f16", fg: "#e0cf9f" },
  bad:   { bg: "#3b1d1d", fg: "#ffb4b4" },
  live:  { bg: "#16283a", fg: "#8ec5ff" },
  muted: { bg: "#22262f", fg: "#8a94a6" },
};
const muted = "var(--text-muted, #8a94a6)";

function Pill({ text, tone }: { text: string; tone: keyof typeof TONE }) {
  const c = TONE[tone];
  return (
    <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 999,
                   background: c.bg, color: c.fg, whiteSpace: "nowrap" }}>{text}</span>
  );
}

/** Метка стадии спрятана внутри заголовка: «[auto] [3/5 Review] название».
 *  Разбираем её на части: работа отдельно, стадия отдельно. */
function parse(raw: string): { base: string; stage: string | null } {
  const m = /^\[auto\]\s*\[(\d+)\/(\d+)\s+([^\]]+)\]\s*(.*)$/.exec(raw || "");
  if (m) return { base: m[4].trim(), stage: m[3].trim() };
  const plain = /^\[auto\]\s*(.*)$/.exec(raw || "");
  return { base: (plain ? plain[1] : raw || "").trim(), stage: null };
}

const LIVE = ["running", "queued", "preparing"];
// Сколько задач старше начала работы должно быть загружено, чтобы мы имели
// право сказать «этой стадии не было», а не «я её не вижу».
const OLDER_ENOUGH = 30;

type Group = {
  base: string;
  items: { task: Task; stage: string | null; verdict?: Verdict }[];
  latest: Task;
  status: { label: string; tone: keyof typeof TONE };
  currentStage: string | null;
  reached: Record<string, "done" | "live" | "bad" | "skipped" | "again">;
  lap?: number;
  meta?: WorkMeta;
  promise?: { files?: string[]; commands?: string[] };
};

// eslint-disable-next-line react-refresh/only-export-components
export function build(tasks: Task[], verdicts: Record<string, Verdict>, questions: Question[],
                      works: Record<string, WorkMeta> = {},
                      statuses: Record<string, { state: string; text: string }> = {},
                      promises: Record<string, { files?: string[]; commands?: string[] }> = {}): Group[] {
  const openQ = new Set(
    questions.filter((q) => q.status === "open").map((q) => q.task_id),
  );
  // Ответ уже есть, но исполнителя нет (лимит подписки): это не вопрос
  // к хозяину, и подписывать это «ждёт твоего ответа» — врать.
  const noWorkerQ = new Set(
    questions.filter((q) => q.status === "no_worker" || q.status === "stuck").map((q) => q.task_id),
  );
  // Состояние вопроса по каждой задаче: открыт — ход владельца, отвечен —
  // ход оркестратора, нет вопроса — ещё никто не разбирался.
  const qState = new Map(questions.map((q) => [q.task_id ?? "", q.status ?? ""]));
  const map = new Map<string, Group>();
  for (const t of tasks) {
    const { base, stage } = parse(t.title);
    const v = verdicts[t.id];
    const g = map.get(base) ?? {
      base, items: [], latest: t,
      status: { label: "", tone: "muted" as const }, currentStage: null, reached: {},
    };
    g.items.push({ task: t, stage: stage ?? v?.stage ?? null, verdict: v });
    if ((t.created_at ?? "") > (g.latest.created_at ?? "")) g.latest = t;
    map.set(base, g);
  }

  for (const g of map.values()) {
    g.items.sort((a, b) => (a.task.created_at ?? "").localeCompare(b.task.created_at ?? ""));
    for (const it of g.items) {
      if (!it.stage) continue;
      if (LIVE.includes(it.task.state)) g.reached[it.stage] = "live";
      else if (it.task.state === "failed") g.reached[it.stage] = g.reached[it.stage] ?? "bad";
      else if (it.task.state === "succeeded") {
        // «Исполнитель закончил» не равно «проверка приняла». Verify может
        // успешно вернуть BLOCKED/FAIL; зелёная стадия в таком случае врёт.
        g.reached[it.stage] = it.verdict?.final_pass === false ? "bad" : "done";
      }
    }
    // Работу могли завести сразу с середины конвейера: разбор и спецификацию
    // человек уже сделал руками. Такие стадии не «не дошли», а «не нужны».
    // Но помечать так можно, только если мы уверены, что начало работы попало
    // в загруженное окно — иначе выдадим «не было» за «не загрузили».
    // Сколько раз работа возвращалась на доработку: считаем по повторам
    // одной и той же стадии.
    const seenStages = new Set<string>();
    let lap = 1;
    for (const it of g.items) {
      if (!it.stage) continue;
      if (seenStages.has(it.stage)) { lap += 1; seenStages.clear(); }
      seenStages.add(it.stage);
    }
    g.lap = lap;

    g.meta = works[g.base];
    g.promise = promises[g.base];
    const recorded = g.meta?.skipped;
    if (recorded && recorded.length) {
      // Записано при заведении работы — гадать не нужно.
      for (const st of recorded) if (!g.reached[st]) g.reached[st] = "skipped";
    } else {
      const firstItem = g.items.find((i) => i.stage);
      const firstAt = firstItem?.task.created_at ?? "";
      const olderLoaded = tasks.filter((t) => (t.created_at ?? "") < firstAt).length;
      if (firstItem?.stage && olderLoaded >= OLDER_ENOUGH) {
        for (const st of STAGE_ORDER) {
          if (st === firstItem.stage) break;
          if (!g.reached[st]) g.reached[st] = "skipped";
        }
      }
    }
    const live = g.items.find((i) => LIVE.includes(i.task.state));
    const waiting = g.items.find((i) => openQ.has(i.task.id));
    const noWorker = g.items.find((i) => noWorkerQ.has(i.task.id));
    const passed = g.items.some((i) => i.verdict?.final_pass === true);
    const rework = g.items.some((i) => i.verdict?.final_pass === false);
    // Сорвалась — только если сорвалась ПОСЛЕДНЯЯ попытка. Одна упавшая
    // стадия в середине истории не делает всю работу проваленной:
    // её могли перезапустить и довести.
    const failed = g.items[g.items.length - 1]?.task.state === "failed";
    const allCancelled = g.items.every((i) => i.task.state === "cancelled");

    if (live) {
      g.currentStage = live.stage;
      // «Заново» относится к повторно запущенной текущей стадии, а не к
      // уже пройденным шагам справа: они остаются историей прошлого круга.
      const liveIndex = g.items.indexOf(live);
      if (live.stage && g.items.slice(0, liveIndex).some((it) => it.stage === live.stage)) {
        g.reached[live.stage] = "again";
      }
      g.status = { label: live.task.state === "queued" ? "ждёт исполнителя" : "идёт", tone: "live" };
    } else if (waiting) {
      g.status = { label: "ждёт твоего ответа", tone: "warn" };
    } else if (noWorker) {
      g.status = { label: "ответ есть, ждёт свободного исполнителя", tone: "warn" };
    } else if (passed) {
      g.status = { label: "работа принята", tone: "ok" };
    } else if (rework) {
      // Ревью вернуло работу — это ход конвейера, а не владельца.
      g.status = { label: "вернули на доработку, продолжаем", tone: "live" };
    } else if (allCancelled) {
      g.status = { label: "отменена", tone: "muted" };
    } else {
      // Кто ходит следующим. Свежий сбой без вопроса — оркестратор ещё не
      // добрался до него: он обходит задачи раз в полминуты. Если прошло
      // много времени и вопроса так и нет — никто не взялся, и это плохо.
      const newest = g.items[g.items.length - 1];
      const qs = newest ? qState.get(newest.task.id) : undefined;
      const ageMin = newest
        ? (Date.now() - Date.parse(newest.task.created_at ?? "")) / 60000
        : 1e9;
      if (qs === "answered") {
        g.status = { label: "оркестратор ответил, продолжаем", tone: "live" };
      } else if (failed && !qs && ageMin < 10) {
        g.status = { label: "сорвалась, оркестратор разбирается", tone: "warn" };
      } else if (failed) {
        g.status = { label: "сорвалась и стоит — никто не взялся", tone: "bad" };
      } else if (!qs && ageMin < 10) {
        g.status = { label: "закончила ход, оркестратор решает", tone: "warn" };
      } else {
        g.status = { label: "остановлена, ждёт решения", tone: "warn" };
      }
    }
  }

  // Правда о том, почему работа стоит. «Вернули на доработку, продолжаем»
  // — ложь, если конвейер по этой работе на паузе или встал совсем.
  for (const g of map.values()) {
    const ws = statuses[g.base];
    if (!ws) continue;
    if (g.items.some((it) => LIVE.includes(it.task.state))) continue;
    if (ws.state === "stopped_owner") g.status = { label: "остановлена: конвейер на паузе", tone: "muted" };
    else if (ws.state === "stuck") g.status = { label: "застряла: сама не двигается", tone: "bad" };
  }

  // Внутри раздела всё сортируется одинаково — по времени, новое сверху.
  // Срочность выражается разделом, а не хитрым весом внутри общего списка:
  // именно из-за такого веса позавчерашняя остановленная работа оказывалась
  // выше вчерашней принятой.
  return [...map.values()].sort(
    (a, b) => (b.latest.created_at ?? "").localeCompare(a.latest.created_at ?? ""),
  );
}

// Возраст, после которого работа уходит в архив, если от неё ничего не ждут.
const FRESH_DAYS = 2;

/** Куда попадёт работа. Порядок разделов — это порядок срочности:
 *  сначала то, что стоит без человека, потом живое, потом свежий итог. */
function sectionOf(g: Group): "waiting" | "live" | "won" | "lost" | "archive" {
  // Закрытую работу владелец видеть в делах не должен, даже если она свежая:
  // от него по ней ничего не ждут и ждать не будут.
  if (g.meta?.closed) return "archive";
  if (g.status.label === "ждёт твоего ответа") return "waiting";
  if (g.status.tone === "bad") return "waiting";
  // Пока ход оркестратора — это не дело владельца, ему туда смотреть незачем.
  if (g.status.label === "оркестратор ответил, продолжаем") return "live";
  if (g.status.label.includes("оркестратор")) return "live";
  if (g.status.tone === "live") return "live";
  const age = Date.now() - Date.parse(g.latest.created_at ?? "");
  const fresh = Number.isFinite(age) && age < FRESH_DAYS * 864e5;
  if (g.status.label === "остановлена" && fresh) return "waiting";
  if (!fresh) return "archive";
  // Итог итогу рознь: принятая работа и брошенная — разные полки.
  return g.status.tone === "ok" ? "won" : "lost";
}

const SECTIONS: { key: "waiting" | "live" | "won" | "lost"; title: string;
                   hint: string; accent: string }[] = [
  { key: "waiting", title: "Нужен ты", hint: "Без тебя не сдвинется", accent: "#ffb86b" },
  { key: "live", title: "Идёт сейчас", hint: "Работает или вот-вот продолжится — от тебя ничего не нужно", accent: "#8ec5ff" },
  { key: "won", title: "Сделано", hint: "Принято за последние два дня — результат можно смотреть", accent: "#7ee2a8" },
  { key: "lost", title: "Не вышло / остановлено", hint: "Закончились без результата — реши, нужны ли они ещё", accent: "#ffb4b4" },
];

export function WorkView({
  tasks, workers, pending, error, fetching, updatedAt,
  onTask, onAnswer, onDelegate, onRefresh, hasMore, loadingMore, onLoadMore,
}: ViewStateProps & {
  tasks?: Task[]; workers?: Worker[]; pending: boolean; error: Error | null;
  onTask: (id: string) => void; onAnswer?: () => void; onDelegate: () => void;
  hasMore: boolean; loadingMore: boolean; onLoadMore: () => void;
}) {
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({});
  const [works, setWorks] = useState<Record<string, WorkMeta>>({});
  const [statuses, setStatuses] = useState<Record<string, { state: string; text: string }>>({});
  const [promises, setPromises] = useState<Record<string, { files?: string[]; commands?: string[] }>>({});
  const [showArchive, setShowArchive] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [history, setHistory] = useState<Record<string, string>>({});
  const [byStage, setByStage] = useState(false);
  const [open, setOpen] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const pull = async () => {
      try {
        const [v, q, wk, ws] = await Promise.all([
          fetch("/api/v1/verdicts"), fetch("/api/v1/questions"), fetch("/api/v1/works"),
          fetch("/api/v1/work-status"),
        ]);
        if (ws.ok && alive) setStatuses((await ws.json()) as Record<string, { state: string; text: string }>);
        try {
          const pr = await fetch("/api/v1/promises");
          if (pr.ok && alive) setPromises((await pr.json()) as Record<string, { files?: string[]; commands?: string[] }>);
        } catch { /* обещаний может не быть */ }
        if (wk.ok && alive) setWorks((await wk.json()) as Record<string, WorkMeta>);
        if (v.ok && alive) setVerdicts(((await v.json()) as { verdicts?: Record<string, Verdict> }).verdicts ?? {});
        if (q.ok && alive) setQuestions(((await q.json()) as { questions?: Question[] }).questions ?? []);
      } catch { /* без вердиктов покажем нейтрально */ }
    };
    void pull();
    const h = window.setInterval(() => void pull(), 20000);
    return () => { alive = false; window.clearInterval(h); };
  }, []);

  useEffect(() => {
    const ids = (tasks ?? []).map((task) => task.id);
    if (!ids.length) return;
    let alive = true;
    const batches: string[][] = [];
    for (let start = 0; start < ids.length; start += 100) batches.push(ids.slice(start, start + 100));
    void Promise.all(batches.map(async (batch) => {
      const query = new URLSearchParams();
      batch.forEach((id) => query.append("task_id", id));
      const response = await fetch(`/api/v1/work-history?${query}`);
      if (!response.ok) return [];
      const data = await response.json() as { history?: HistoryEntry[] };
      return data.history ?? [];
    })).then((results) => {
      if (alive) setHistory(Object.fromEntries(results.flat().map((item) => [item.task_id, item.text])));
    }).catch(() => { /* без краткой истории остаётся обычный статус */ });
    return () => { alive = false; };
  }, [tasks]);

  // Хук обязан вызываться до любых ранних выходов, иначе на втором
  // рендере их станет меньше и React уронит весь экран.
  const projectName = useProjectName();

  if (pending) return <LoadingState label="Загружаю работу" />;
  if (error && !tasks) return <ErrorState error={error} onRetry={onRefresh} />;

  const workerMap = new Map((workers ?? []).map((w) => [w.id, w]));
  const groups = build(tasks ?? [], verdicts, questions, works, statuses, promises);

  return (
    <div className="page page-work">
      <ViewHeader title="Работа агентов" fetching={fetching} updatedAt={updatedAt} onRefresh={onRefresh} />
      {error && <StaleBanner error={error} />}

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "4px 0 14px", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: muted }}>
          {byStage ? "Каждая карточка — отдельный этап." : "Сверху то, что стоит без тебя. Ниже — что идёт и что уже сделано. Старое в архиве."}
        </span>
        <span style={{ flex: 1 }} />
        <button className="button" onClick={() => setByStage((v) => !v)}>
          {byStage ? <><Rows3 size={14} /> Показать по работам</> : <><LayoutGrid size={14} /> Показать по этапам</>}
        </button>
      </div>

      {(tasks ?? []).length === 0 ? (
        <EmptyState
          icon={<ListChecks size={22} />}
          title="Работы пока нет"
          description="Поставь первую задачу — она останется здесь даже после перезапуска."
          action={<button className="button button-primary" onClick={onDelegate}><Plus size={16} /> Поставить задачу</button>}
        />
      ) : byStage ? (
        <StageBoard tasks={tasks ?? []} verdicts={verdicts} workerMap={workerMap} onTask={onTask} />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {SECTIONS.map((sec) => {
            const rows = groups.filter((g) => sectionOf(g) === sec.key);
            if (!rows.length) return null;
            return (
              <div key={sec.key} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10,
                              borderLeft: "3px solid " + sec.accent, paddingLeft: 10 }}>
                  <h2 style={{ fontSize: 15, margin: 0, color: sec.accent }}>{sec.title}</h2>
                  <span style={{
                    fontSize: 11, color: muted, border: "1px solid var(--border, #262c38)",
                    borderRadius: 999, padding: "1px 8px",
                  }}>{rows.length}</span>
                  <span style={{ fontSize: 12.5, color: muted }}>{sec.hint}</span>
                </div>
                {rows.map((g) => (
                  <GroupRow key={g.base} g={g} workerMap={workerMap}
                            expanded={open === g.base}
                            onToggle={() => setOpen(open === g.base ? "" : g.base)}
                            onTask={onTask} onAnswer={onAnswer}
                            history={history}
                            project={projectName(g.latest.repository_id)} />
                ))}
              </div>
            );
          })}

          {(() => {
            const old = groups.filter((g) => sectionOf(g) === "archive");
            if (!old.length) return null;
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <button className="button" onClick={() => setShowArchive((v) => !v)}
                        style={{ alignSelf: "flex-start" }}>
                  {showArchive ? "Свернуть архив" : `Архив · ${old.length}`}
                </button>
                {!showArchive && (
                  <span style={{ fontSize: 12.5, color: muted }}>
                    Закрытые работы и всё, что старше двух дней и никого не ждёт.
                  </span>
                )}
                {showArchive && old.map((g) => (
                  <GroupRow key={g.base} g={g} workerMap={workerMap}
                            expanded={open === g.base}
                            onToggle={() => setOpen(open === g.base ? "" : g.base)}
                            onTask={onTask} onAnswer={onAnswer}
                            history={history}
                            project={projectName(g.latest.repository_id)} />
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {hasMore && (
        <div className="load-more">
          <button className="button button-secondary" onClick={onLoadMore} disabled={loadingMore}>
            {loadingMore ? "Загружаю…" : "Показать ещё"}
          </button>
        </div>
      )}
    </div>
  );
}

function GroupRow({ g, workerMap, expanded, onToggle, onTask, onAnswer, history, project }: {
  g: Group; workerMap: Map<string, Worker>; expanded: boolean;
  onToggle: () => void; onTask: (id: string) => void; onAnswer?: () => void;
  history: Record<string, string>;
  project?: string;
}) {
  const worker = workerMap.get(g.latest.worker_id);
  // Самая свежая ссылка «посмотреть» по всей работе: её называет стадия
  // разработки, а принимается работа позже — искать надо по всем шагам.
  // Дверь называет последняя стадия, которая реально смотрела результат.
  // Черновые ссылки старых кругов разработки не должны перебивать её:
  // они уже уводили хозяина на чужой экран.
  const byStage = (st: string) => [...g.items].reverse()
    .filter((it) => it.stage === st).map((it) => it.verdict?.try_url).find(Boolean);
  const tryUrl = byStage("Verify") ?? byStage("Review") ?? [...g.items].reverse()
    .map((it) => it.verdict?.try_url).find(Boolean) ?? "";
  // «Готово, когда» — перевод сути в проверяемые факты. Показываем сразу
  // после Спецификации: владелец может сказать «я просил другое» до того,
  // как потрачен хоть один круг разработки.
  const proofTxt = [...g.items].reverse()
    .filter((it) => it.stage === "Verify")
    .map((it) => it.verdict?.proof).find(Boolean) ?? "";
  const proofShort = proofTxt.length > 110
    ? proofTxt.slice(0, Math.max(proofTxt.lastIndexOf(" ", 110), 80)) + "…"
    : proofTxt;
  const promiseLine = g.promise && ((g.promise.files?.length ?? 0) + (g.promise.commands?.length ?? 0) > 0)
    ? [...(g.promise.files ?? []).map((f) => `файл ${f}`),
       ...(g.promise.commands ?? []).map((c) => `команда: ${c}`)].join(" · ")
    : "";
  return (
    <section style={{
      background: "var(--surface, #171b24)", border: "1px solid var(--border, #262c38)",
      borderColor: g.status.tone === "live" ? "#2a4560" : g.status.tone === "warn" ? "#4a3f22" : "var(--border, #262c38)",
      borderRadius: 12, padding: "12px 16px",
      minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere",
    }}>
      {promiseLine && (
        <details style={{ fontSize: 12, color: "#9fb4d8", margin: "0 0 6px" }}>
          <summary style={{ cursor: "pointer", listStyle: "none", overflow: "hidden",
                            textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                   title="Обещания Спецификации: по ним машина сверяет дифф, а Проверка гоняет команды">
            готово, когда: {promiseLine}
          </summary>
          <div style={{ marginTop: 4, lineHeight: 1.5, overflowWrap: "anywhere",
                        wordBreak: "break-all" }}>{promiseLine}</div>
        </details>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", cursor: "pointer" }}
           onClick={onToggle}>
        {g.status.label === "работа принята" && !tryUrl && proofTxt && !g.meta?.closed && (
          <span title="Результат не видно на экране — вот как машина его подтвердила"
                style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 999,
                         background: "#16341f", color: "#7ee2a8", border: "1px solid #2f5741" }}>
            принята · {proofShort}
          </span>
        )}
        {g.status.label === "работа принята" && tryUrl && !g.meta?.closed ? (
          // Итог принят — значит изменение уже на стенде. Сама плашка и есть
          // дверь туда: «сделано» без возможности посмотреть — просто слово.
          <a href={tryUrl} target="_blank" rel="noreferrer"
             onClick={(e) => e.stopPropagation()}
             title="Открыть страницу, где видно сделанное"
             style={{
               fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
               background: "#16341f", color: "#7ee2a8", border: "1px solid #2f5741",
               textDecoration: "none", whiteSpace: "nowrap",
             }}>работа принята · посмотреть →</a>
        ) : g.status.label === "ждёт твоего ответа" && onAnswer ? (
          // Плашка про долг перед владельцем обязана вести туда, где долг
          // закрывают. Сообщить о проблеме и не дать способа её решить —
          // худший вид экрана.
          <button
            onClick={(e) => { e.stopPropagation(); onAnswer(); }}
            title="Открыть экран, где можно ответить"
            style={{
              fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
              background: "#4a3f22", color: "#e0cf9f", border: "1px solid #7a6a3a",
              cursor: "pointer", whiteSpace: "nowrap",
            }}>ждёт твоего ответа →</button>
        ) : (
          <Pill text={g.meta?.closed ? "закрыта" : g.status.label}
                tone={g.meta?.closed ? "muted" : g.status.tone} />
        )}
        {project && <ProjectTag name={project} />}
        {g.meta?.origin && (
          <span
            title={g.meta.reason || undefined}
            style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 999, whiteSpace: "nowrap",
              border: "1px solid",
              borderColor: g.meta.origin === "owner" ? "#3d6a92" : "#4a4160",
              color: g.meta.origin === "owner" ? "#8ec5ff" : "#c3aef0",
              background: "transparent",
            }}>{ORIGIN_RU[g.meta.origin] ?? g.meta.origin}</span>
        )}
        <strong style={{ fontSize: 15, opacity: g.meta?.closed ? 0.65 : 1 }}>{g.base}</strong>
        {(g.lap ?? 1) > 1 && (
          <span title="Работа возвращалась на доработку — идёт повторный круг"
                style={{ fontSize: 11, padding: "2px 8px", borderRadius: 999,
                         border: "1px solid #5c4f2a", color: "#e0cf9f",
                         whiteSpace: "nowrap" }}>круг {g.lap}</span>
        )}
        {g.meta?.closed_reason && (
          <span style={{ fontSize: 12, color: muted }}>· {g.meta.closed_reason}</span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: muted }}>
          {worker?.name ?? ""} · {timeAgo(g.latest.created_at)}
        </span>
        <ChevronRight size={14} style={{ transform: expanded ? "rotate(90deg)" : undefined, color: muted }} />
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
        {(() => {
          const idxNow = g.currentStage ? STAGE_ORDER.indexOf(g.currentStage) : -1;
          const maxIdx = STAGE_ORDER.reduce((m, x, i) => (g.reached[x] ? i : m), -1);
          return STAGE_ORDER.map((st, idx) => {
            const s = g.reached[st];
            const isNow = g.currentStage === st;
            // Этап никогда не проводился, но работа уже дальше него:
            // значит, он и не понадобится (например, разбор сделан в плане
            // эпика). Честная подпись вместо немого серого.
            const skipped = s === "skipped" || (!s && !isNow && idx < maxIdx);
            const again = s === "again";
            // Зелёное позади возврата — история прошлого круга, а не текущее
            // состояние: после «Разработка — заново» Ревью пройдёт снова.
            const past = s === "done" && idxNow >= 0 && idx > idxNow;
            const bg = past ? "#1a2620" : s === "done" ? "#2f5741" : s === "bad" ? "#5a2b2b"
                     : isNow ? "#2a4560" : "#232833";
            const fg = past ? "#5f8f74" : s === "done" ? "#7ee2a8" : s === "bad" ? "#ffb4b4"
                     : isNow ? "#8ec5ff" : "#5a6270";
            return (
              <span key={st}
                title={skipped ? "Стадию не проводили: работа началась с более позднего шага (например, разбор уже сделан в плане эпика)"
                     : past ? "Этап проходил в прошлом круге; после возврата в разработку он будет пройден заново"
                     : again ? "Этап идёт повторно после возврата"
                     : (s ? undefined : "Стадия ещё не пройдена")}
                style={{
                  fontSize: 11.5, padding: "3px 10px", borderRadius: 6,
                  background: skipped ? "transparent" : again ? "#3a3320" : bg,
                  color: skipped ? "#4a515e" : again ? "#e0cf9f"
                       : (s || isNow ? fg : "#5a6270"),
                  border: isNow ? "1px solid #3d6a92"
                        : skipped ? "1px dashed #363d4a"
                        : past ? "1px dashed #2f5741"
                        : again ? "1px solid #5c4f2a" : "1px solid transparent",
                }}>{skipped ? `${STAGE_RU[st]} — не нужна`
                    : past ? `${STAGE_RU[st]} — прошлый круг`
                    : again ? `${STAGE_RU[st]} — заново`
                    : s === "bad" ? `${STAGE_RU[st]} — не прошла`
                    : STAGE_RU[st]}</span>
            );
          });
        })()}
      </div>

      {expanded && (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--border, #262c38)", paddingTop: 10,
                      display: "flex", flexDirection: "column", gap: 6 }}>
          {g.items.map(({ task, stage, verdict }, idx) => {
            const isLast = idx === g.items.length - 1;
            // «Остановлена» уместно только для последнего шага. У прежних шагов
            // ход просто закончился, и работа поехала дальше — это не остановка.
            const stopped = verdict?.action === "stop";
            const label =
              LIVE.includes(task.state) ? "идёт"
              : task.state === "failed" ? "сорвалась"
              : task.state === "cancelled" ? "отменена"
              : verdict?.final_pass === true ? "проверка пройдена"
              : verdict?.final_pass === false ? "на доработку"
              : verdict?.action === "advance" ? "этап пройден"
              : stopped && !isLast && stage === "Review" ? "вернул на доработку"
              : stopped && !isLast ? "ход закончен, работа пошла дальше"
              : stopped ? "остановлена, ждёт решения"
              : "отработала";
            const tone =
              LIVE.includes(task.state) ? "live"
              : task.state === "failed" ? "bad"
              : task.state === "cancelled" ? "muted"
              : verdict?.final_pass === false ? "warn"
              : verdict?.final_pass === true || verdict?.action === "advance" ? "ok"
              : stopped && !isLast ? "muted"
              : stopped ? "warn" : "muted";
            return (
            <div key={task.id}
                 onClick={() => onTask(task.id)}
                 style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
                          fontSize: 12.5, cursor: "pointer", padding: "3px 0" }}>
              <span style={{ minWidth: 110, color: "#8ec5ff" }}>
                {stage ? STAGE_RU[stage] ?? stage : "—"}
              </span>
              <Pill text={label} tone={tone as keyof typeof TONE} />
              {history[task.id] && <span style={{ color: muted }}>{history[task.id]}</span>}
              <span style={{ color: muted }}>
                {workerMap.get(task.worker_id)?.name ?? "—"} · {timeAgo(task.created_at)}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ color: muted }}>открыть ›</span>
            </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

/** Старый вид: по этапам. Оставлен как второй режим — иногда нужно именно так. */
function StageBoard({ tasks, verdicts, workerMap, onTask }: {
  tasks: Task[]; verdicts: Record<string, Verdict>;
  workerMap: Map<string, Worker>; onTask: (id: string) => void;
}) {
  const COLUMNS: Record<string, { title: string; empty: string }> = {
    queued:    { title: "В очереди",  empty: "Очередь пуста" },
    running:   { title: "В работе",   empty: "Сейчас никто не работает" },
    succeeded: { title: "Отработали", empty: "Пока пусто" },
    failed:    { title: "Сорвались",  empty: "Срывов нет" },
    cancelled: { title: "Отменены",   empty: "Отменённых нет" },
  };
  const grouped = Object.fromEntries(
    taskStates.map((s) => [s, tasks.filter((t) => t.state === s)]),
  ) as Record<TaskState, Task[]>;

  return (
    <div className="work-board" data-testid="work-board">
      {taskStates.map((state) => {
        const col = COLUMNS[state] ?? { title: state, empty: "Пусто" };
        return (
          <section className="work-column" key={state}>
            <div className="column-heading">
              <span className={`status-dot status-${state}`} aria-hidden="true" />
              <h2>{col.title}</h2>
              <span className="count">{grouped[state].length}</span>
            </div>
            <div className="task-stack">
              {grouped[state].length === 0 ? <div className="column-empty">{col.empty}</div> : (
                grouped[state].map((task) => {
                  const { base, stage } = parse(task.title);
                  const v = verdicts[task.id];
                  const st = stage ?? v?.stage ?? null;
                  const i = st ? STAGE_ORDER.indexOf(st) : -1;
                  const w = workerMap.get(task.worker_id);
                  return (
                    <button className="task-card" key={task.id} onClick={() => onTask(task.id)}>
                      <span style={{ fontSize: 11, color: "#8ec5ff", marginBottom: 4 }}>
                        {i >= 0 ? `${i + 1} из ${STAGE_ORDER.length} · ${STAGE_RU[st!]}` : "поставлена вручную"}
                      </span>
                      <span className="task-title">{base}</span>
                      <div className="task-meta">
                        <span>{w?.name ?? "—"}</span>
                        <span aria-hidden="true">·</span>
                        {w && <><span>{runtimeLabel(w.runtime)}</span><span aria-hidden="true">·</span></>}
                        <span>{timeAgo(task.created_at)}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
