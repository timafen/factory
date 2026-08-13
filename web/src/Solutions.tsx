import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useVisibleInterval } from "./polling";
import type { OwnerQuestion } from "./types";

const statusLabels: Record<string, string> = {
  open: "Открыт",
  answered: "Отвечен",
  resolved: "Решён",
  stale: "Устарел",
};

function displayDate(value?: string): string {
  if (!value) return "Дата не указана";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusLabel(status: string): string {
  return statusLabels[status] ?? status;
}

export function SolutionsView() {
  const interval = useVisibleInterval(10_000);
  const questions = useQuery({
    queryKey: ["questions"],
    queryFn: async (): Promise<OwnerQuestion[]> => {
      const response = await fetch("/api/v1/questions");
      if (!response.ok) throw new Error(`questions ${response.status}`);
      return ((await response.json()).questions ?? []) as OwnerQuestion[];
    },
    refetchInterval: interval,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 820 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <p style={{ margin: 0, color: "var(--text-muted, #8a94a6)", flex: 1 }}>
          История всех вопросов конвейера. Здесь можно только посмотреть сохранённые решения.
        </p>
        <button className="button" aria-label="Обновить список решений" onClick={() => void questions.refetch()}>
          <RefreshCw size={15} /> Обновить
        </button>
      </div>

      {questions.isPending && <div className="quiet-empty">Загружаю историю решений…</div>}
      {questions.isError && <div className="quiet-empty" role="alert">Не удалось загрузить историю решений. Попробуйте обновить список.</div>}
      {!questions.isPending && !questions.isError && questions.data?.length === 0 && (
        <div className="quiet-empty">История решений пока пуста.</div>
      )}
      {questions.data?.map((question) => (
        <article key={question.id} aria-label={`Решение: ${question.title}`} style={{ background: "var(--surface, #171b24)", border: "1px solid #3a4a5f", borderRadius: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999, background: "#3b2f1d", color: "#e0cf9f" }}>{question.stage}</span>
            <strong style={{ fontSize: 15 }}>{question.title}</strong>
            <span style={{ fontSize: 12, color: "var(--text-muted, #8a94a6)" }}>Статус: {statusLabel(question.status)}</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
            Дата вопроса: <time dateTime={question.asked_at}>{displayDate(question.asked_at)}</time>
          </div>
          {question.situation && <p style={{ margin: 0, fontSize: 14, whiteSpace: "pre-wrap" }}>Ситуация: {question.situation}</p>}
          {question.question && <p style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#8ec5ff", whiteSpace: "pre-wrap" }}>Вопрос: {question.question}</p>}
          {question.answer && <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>Ответ: {question.answer}</p>}
          {(question.answered_by || question.answered_at) && (
            <div style={{ fontSize: 13, color: "var(--text-muted, #8a94a6)" }}>
              Ответил: {question.answered_by ?? "не указан"}{question.answered_at && <> · <time dateTime={question.answered_at}>{displayDate(question.answered_at)}</time></>}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
