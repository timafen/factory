import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

const statusLabel = { pending: "Ожидает сборки", running: "Собирается", ready: "Готов", error: "Не удалось собрать" } as const;

export function Reports() {
  const reports = useQuery({ queryKey: ["daily-reports"], queryFn: api.dailyReports });
  if (reports.isPending) return <p>Загружаем отчёты…</p>;
  if (reports.error) return <p role="alert">Не удалось загрузить отчёты.</p>;
  return <div className="reports"><h1>Ежедневные отчёты</h1><p>Метрики конвейера и снимки изменённых экранов — день к дню.</p>
    {(reports.data ?? []).map(report => <article className="report-card" key={`${report.report_date}-${report.timezone}`}>
      <h2>{report.report_date}</h2><p>{report.timezone} · {statusLabel[report.status]}</p>
      {report.error && <p className="report-error">Причина: {report.error}</p>}
      {report.status === "ready" && <a className="button button-primary" href={`/api/v1/reports/daily/${report.report_date}/pdf?timezone=${encodeURIComponent(report.timezone)}`}>Скачать PDF</a>}
    </article>)}
    {(reports.data ?? []).length === 0 && <p>Отчётов пока нет.</p>}
  </div>;
}
