import {
  ArrowLeft,
  CheckCircle2,
  GitBranch,
  LoaderCircle,
  Plus,
  Server,
  XCircle,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "./api";
import { useVisibleInterval } from "./polling";
import type { ManagedRepository } from "./types";
import {
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  PanelHeading,
  StaleBanner,
  ViewHeader,
} from "./ui";

function lastUpdated(value: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 10) return "только что";
  if (seconds < 60) return `${seconds} с назад`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} дн. назад`;
}

function readinessReason(reason: string): string {
  const labels: Record<string, string> = {
    "Repository routing is disabled.": "Маршрутизация в репозиторий выключена.",
    "Repository source is not supported for managed acquisition.": "Источник репозитория не поддерживает управляемое получение.",
    "Worker is offline.": "Исполнитель не в сети.",
    "Worker is unhealthy.": "Исполнитель неисправен.",
    "Worker does not currently report GitHub access.": "Исполнитель не сообщает о доступе к GitHub.",
    "Another advertised repository uses this routing identity.": "Другой заявленный репозиторий использует эту идентичность маршрутизации.",
    "Worker cannot acquire managed repositories and does not advertise this one.": "Исполнитель не может получать управляемые репозитории и не заявил этот.",
    "Managed repository cache and reservations are full.": "Кэш и резервирования управляемых репозиториев заполнены.",
    "Repository retained-worktree capacity is full.": "Лимит сохранённых рабочих копий репозитория исчерпан.",
    "Online, healthy, with GitHub access and this repository cached.": "В сети, исправен, есть доступ к GitHub и репозиторий в кэше.",
    "Online, healthy, with GitHub access and this repository advertised.": "В сети, исправен, есть доступ к GitHub и репозиторий заявлен.",
    "Online, healthy, with GitHub access and managed cache headroom.": "В сети, исправен, есть доступ к GitHub и место в управляемом кэше.",
  };
  return labels[reason] ?? reason;
}

export function RepositoriesView({ onRepository }: { onRepository: (id: string) => void }) {
  const interval = useVisibleInterval(10_000);
  const queryClient = useQueryClient();
  const repositories = useQuery({
    queryKey: ["repositories"],
    queryFn: api.repositories,
    refetchInterval: interval,
  });
  const [remoteIdentity, setRemoteIdentity] = useState("");
  const [duplicate, setDuplicate] = useState<ManagedRepository | null>(null);
  const create = useMutation({
    mutationFn: () => api.createRepository(remoteIdentity),
    onSuccess: ({ repository, created }) => {
      queryClient.setQueryData<ManagedRepository[]>(["repositories"], (current) => {
        const next = [...(current ?? []).filter((item) => item.id !== repository.id), repository];
        return next.sort((left, right) => left.remote_identity.localeCompare(right.remote_identity));
      });
      if (!created) {
        setDuplicate(repository);
        return;
      }
      setRemoteIdentity("");
      setDuplicate(null);
      onRepository(repository.id);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (remoteIdentity.trim()) create.mutate();
  };

  if (repositories.isPending) return <LoadingState label="Загружаем репозитории" />;
  if (!repositories.data) {
    return <ErrorState error={repositories.error} onRetry={() => void repositories.refetch()} />;
  }
  const enabled = repositories.data.filter((repository) => repository.enabled).length;

  return (
    <div className="page repositories-page">
      <ViewHeader
        title="Репозитории"
        fetching={repositories.isFetching}
        updatedAt={repositories.dataUpdatedAt}
        onRefresh={() => void repositories.refetch()}
      />
      {repositories.error && <StaleBanner error={repositories.error} />}

      <section className="panel repository-add-panel">
        <PanelHeading title="Добавить репозиторий GitHub" aside="Включён после добавления" />
        <form className="repository-add-form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="repository-identity">Точная идентичность</label>
            <input
              id="repository-identity"
              value={remoteIdentity}
              onChange={(event) => {
                setRemoteIdentity(event.target.value);
                setDuplicate(null);
                if (create.error) create.reset();
              }}
              placeholder="github.com/owner/repository"
              autoComplete="off"
              spellCheck={false}
              aria-invalid={Boolean(create.error)}
            />
            <span className="field-hint">GitHub — единственный управляемый провайдер в этой версии.</span>
          </div>
          <button
            className="button button-primary"
            type="submit"
            disabled={!remoteIdentity.trim() || create.isPending}
          >
            {create.isPending ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}
            Добавить репозиторий
          </button>
        </form>
        <InlineError error={create.error} />
        {duplicate && (
          <div className="repository-duplicate" role="status">
            <span><strong>{duplicate.remote_identity}</strong> уже управляется Factory.</span>
            <button className="button button-secondary" onClick={() => onRepository(duplicate.id)}>
              Открыть существующий репозиторий
            </button>
          </div>
        )}
      </section>

      {repositories.data.length === 0 ? (
        <EmptyState
          icon={<GitBranch size={22} />}
          title="Управляемых репозиториев пока нет"
          description="Добавь репозиторий GitHub выше, чтобы исправные исполнители могли брать для него работы."
        />
      ) : (
        <>
          <div className="repository-summary" aria-label="Сводка репозиториев">
            <span>{repositories.data.length} всего</span>
            <span className="healthy-text">{enabled} включено</span>
            <span>{repositories.data.length - enabled} выключено</span>
          </div>
          <div className="managed-repository-list">
            {repositories.data.map((repository) => (
              <button
                className="managed-repository-row"
                key={repository.id}
                onClick={() => onRepository(repository.id)}
              >
                <GitBranch size={17} aria-hidden="true" />
                <span>
                  <strong>{repository.remote_identity}</strong>
                  <small>Обновлён: {lastUpdated(repository.updated_at)}</small>
                </span>
                <span className={`status-badge ${repository.enabled ? "status-succeeded" : "status-cancelled"}`}>
                  <span className="status-dot" />{repository.enabled ? "Включён" : "Выключен"}
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function RepositoryDetail({
  id,
  onBack,
}: {
  id: string;
  onBack: () => void;
}) {
  const interval = useVisibleInterval(10_000);
  const queryClient = useQueryClient();
  const repository = useQuery({
    queryKey: ["repository", id],
    queryFn: () => api.repository(id),
    refetchInterval: interval,
  });
  const readiness = useQuery({
    queryKey: ["repository-readiness", id],
    queryFn: () => api.repositoryReadiness(id),
    refetchInterval: interval,
  });
  const [confirming, setConfirming] = useState(false);
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.setRepositoryEnabled(id, enabled),
    onSuccess: (updated) => {
      queryClient.setQueryData(["repository", id], updated);
      queryClient.setQueryData<ManagedRepository[]>(["repositories"], (current) =>
        current?.map((item) => item.id === updated.id ? updated : item),
      );
      void queryClient.invalidateQueries({ queryKey: ["repository-readiness", id] });
      setConfirming(false);
    },
  });

  if (repository.isPending || readiness.isPending) return <LoadingState label="Загружаем репозиторий" />;
  if (!repository.data || !readiness.data) {
    return (
      <ErrorState
        error={repository.error ?? readiness.error}
        onRetry={() => void Promise.all([repository.refetch(), readiness.refetch()])}
      />
    );
  }
  const data = repository.data;
  const facts = readiness.data.workers;
  const readyWorkers = facts.filter((fact) => fact.ready);
  const cachedWorkers = facts.filter((fact) => fact.cached);
  const advertisedWorkers = facts.filter((fact) => fact.advertised);
  const readySummary = readyWorkers.length === 1
    ? "1 исполнитель готов взять работу"
    : `${readyWorkers.length} исполнителей готовы взять работу`;

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Все репозитории</button>
      <div className="detail-heading repository-detail-heading">
        <div>
          <span className="eyebrow">Управляемый репозиторий GitHub</span>
          <h1>{data.remote_identity}</h1>
          <p>Добавлен: {new Date(data.created_at).toLocaleString()}</p>
        </div>
        <div className="detail-actions">
          {confirming ? (
            <div className="confirm-action">
              <span>
                После выключения новые работы не будут направляться сюда. Уже поставленные и активные работы сохранят этот репозиторий.
              </span>
              <button className="button button-secondary" onClick={() => setConfirming(false)}>Оставить включённым</button>
              <button
                className="button button-danger"
                onClick={() => toggle.mutate(false)}
                disabled={toggle.isPending}
              >
                Выключить маршрутизацию
              </button>
            </div>
          ) : data.enabled ? (
            <button className="button button-danger-secondary" onClick={() => setConfirming(true)}>
              Выключить репозиторий
            </button>
          ) : (
            <button
              className="button button-primary"
              onClick={() => toggle.mutate(true)}
              disabled={toggle.isPending}
            >
              Включить репозиторий
            </button>
          )}
        </div>
      </div>
      {repository.error && <StaleBanner error={repository.error} />}
      {readiness.error && <StaleBanner error={readiness.error} />}
      <InlineError error={toggle.error} />

      <section className={`readiness-banner ${readiness.data.routing_ready ? "ready" : "not-ready"}`}>
        {readiness.data.routing_ready ? <CheckCircle2 size={19} /> : <XCircle size={19} />}
        <div>
          <strong>
            {!data.enabled
              ? "Маршрутизация выключена"
              : readiness.data.routing_ready
                ? readySummary
                : "Сейчас ни один исполнитель не может взять работу"}
          </strong>
          <span>
            {!data.enabled
              ? "Новые работы будут отклоняться, пока репозиторий не включён."
              : "Панель управления использует для маршрутизации те же актуальные данные об исполнителе, резервировании, кэше и сохранении."}
          </span>
        </div>
      </section>

      <div className="repository-detail-layout">
        <section className="panel">
          <PanelHeading title="Готовность исполнителей" aside={`${facts.length} зарегистрировано`} />
          {facts.length === 0 ? (
            <div className="quiet-empty">Нет зарегистрированных исполнителей.</div>
          ) : (
            <div className="repository-worker-list">
              {facts.map((fact) => (
                <div className="repository-worker-row" key={fact.id}>
                  <span className="worker-avatar"><Server size={15} /></span>
                  <span>
                    <strong>{fact.name}</strong>
                    <small>{readinessReason(fact.reason)}</small>
                  </span>
                  <span className="repository-worker-facts">
                    {fact.cached && <span className="tag">В кэше</span>}
                    {fact.advertised && <span className="tag">Заявлен</span>}
                    <span className={fact.ready ? "healthy-text" : "danger-text"}>
                      {fact.ready ? "Готов" : "Не готов"}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <aside className="panel repository-profile-panel">
          <PanelHeading title="Репозиторий" />
          <dl className="metadata">
            <div><dt>Статус</dt><dd>{data.enabled ? "Включён" : "Выключен"}</dd></div>
            <div><dt>Готовы</dt><dd>{readyWorkers.length} исполнителей</dd></div>
            <div><dt>В кэше</dt><dd>{cachedWorkers.length} исполнителей</dd></div>
            <div><dt>Заявили</dt><dd>{advertisedWorkers.length} исполнителей</dd></div>
            <div><dt>Обновлён</dt><dd>{lastUpdated(data.updated_at)}</dd></div>
          </dl>
          <div className="profile-divider" />
          <span className="profile-label">ID репозитория</span>
          <span className="worker-id" title={data.id}>{data.id}</span>
        </aside>
      </div>
    </div>
  );
}
