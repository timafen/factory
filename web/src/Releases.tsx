import { Rocket } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "./api";
import { useVisibleInterval } from "./polling";
import type { ReleaseInfo } from "./types";
import { ErrorState, LoadingState, StaleBanner, ViewHeader } from "./ui";

export function ReleasesView() {
  const interval = useVisibleInterval(15_000);
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    refetchInterval: interval,
  });

  if (dashboard.isPending) return <LoadingState label="Loading releases" />;
  if (dashboard.error && !dashboard.data) {
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  }

  const release: ReleaseInfo = dashboard.data?.release ?? {};

  return (
    <div className="page page-releases">
      <ViewHeader
        title="Релизы"
        fetching={dashboard.isFetching}
        updatedAt={dashboard.dataUpdatedAt}
        onRefresh={() => void dashboard.refetch()}
      />
      {dashboard.error && <StaleBanner error={dashboard.error} />}

      <div className="release-grid">
        <ReleaseCard title="Главная ветка" commit={release.main_head} subject={release.main_subject} />
        <ReleaseCard
          title="Стенд"
          commit={release.staging_release?.commit}
          subject={release.staging_release?.subject}
          health={release.staging_health}
          showHealth
          comparison={compareToMain(
            "Стенд",
            release.staging_release?.commit,
            release.main_head,
            release.staging_in_main,
          )}
        />
        <ReleaseCard
          title="Прод"
          commit={release.prod_release?.commit}
          subject={release.prod_release?.subject}
          health={release.prod_health}
          showHealth
          comparison={compareToMain(
            "Прод",
            release.prod_release?.commit,
            release.main_head,
            release.prod_in_main,
            release.prod_commit_known,
          )}
          action={
            <>
              <button className="button button-secondary" disabled>
                <Rocket size={15} /> Выкатить в прод
              </button>
              <small className="release-action-caption">доступ к записи в прод выключен</small>
            </>
          }
        />
      </div>
    </div>
  );
}

function ReleaseCard({
  title,
  commit,
  subject,
  health,
  showHealth,
  comparison,
  action,
}: {
  title: string;
  commit?: string | null;
  subject?: string | null;
  health?: boolean | string | null;
  showHealth?: boolean;
  comparison?: string | null;
  action?: ReactNode;
}) {
  return (
    <article className="release-card">
      <div className="release-card-heading">
        <h2>{title}</h2>
        {showHealth && <HealthBadge health={health} />}
      </div>
      <div className="release-commit">
        <span className="release-commit-hash">{shortCommit(commit)}</span>
        <span className="release-commit-subject">{subject?.trim() || "Заголовок коммита неизвестен"}</span>
      </div>
      {comparison && <p className="release-comparison">{comparison}</p>}
      {action && <div className="release-card-action">{action}</div>}
    </article>
  );
}

function HealthBadge({ health }: { health: boolean | string | null | undefined }) {
  const { label, tone } = describeHealth(health);
  return (
    <span className={`status-badge status-${tone}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

function describeHealth(
  health: boolean | string | null | undefined,
): { label: string; tone: "healthy" | "error" | "pending" } {
  if (health === true) return { label: "отвечает", tone: "healthy" };
  if (health === false) return { label: "не отвечает", tone: "error" };
  if (typeof health === "string" && health.trim()) {
    const normalized = health.trim().toLowerCase();
    if (["healthy", "ok", "up", "reachable"].includes(normalized)) {
      return { label: "отвечает", tone: "healthy" };
    }
    if (["unhealthy", "down", "error", "unreachable"].includes(normalized)) {
      return { label: "не отвечает", tone: "error" };
    }
    return { label: health, tone: "pending" };
  }
  return { label: "нет данных", tone: "pending" };
}

function shortCommit(commit?: string | null): string {
  if (!commit) return "—";
  return commit.slice(0, 9);
}

function compareToMain(
  target: "Стенд" | "Прод",
  commit: string | null | undefined,
  mainHead: string | null | undefined,
  inMain: boolean | null | undefined,
  commitKnown?: boolean | null,
): string | null {
  if (commitKnown === false) {
    return `${target} собран из кода, которого нет в репозитории.`;
  }
  if (!commit || !mainHead || inMain === undefined || inMain === null) return null;
  if (!inMain) return `${target} собран из кода, которого нет в главной ветке.`;
  if (commit === mainHead) return `${target} собран из главной ветки.`;
  return `${target} отстал от главной ветки.`;
}
