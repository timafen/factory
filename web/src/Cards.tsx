import { ArrowLeft, ExternalLink, FileText, LoaderCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "./api";
import type { CardSummary } from "./types";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PanelHeading,
  ViewHeader,
} from "./ui";

function repoShort(identity: string): string {
  const parts = identity.split("/");
  return parts[parts.length - 1] || identity;
}

function statusTone(status: string | undefined): string {
  const value = (status ?? "").toLowerCase();
  if (!value) return "status-cancelled";
  if (/(released|done|complete|pass|merged)/.test(value)) return "status-succeeded";
  if (/(blocked|fail|stalled|risk)/.test(value)) return "status-failed";
  return "status-running";
}

export function CardsView() {
  const [selected, setSelected] = useState<CardSummary | null>(null);
  const cards = useQuery({ queryKey: ["cards"], queryFn: api.cards, staleTime: 60_000 });

  const grouped = useMemo(() => {
    const groups = new Map<string, CardSummary[]>();
    for (const card of cards.data ?? []) {
      const key = card.repository_identity;
      const list = groups.get(key) ?? [];
      list.push(card);
      groups.set(key, list);
    }
    for (const list of groups.values()) list.sort((a, b) => a.name.localeCompare(b.name));
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [cards.data]);

  if (selected) {
    return <CardDetail card={selected} onBack={() => setSelected(null)} />;
  }
  if (cards.isPending) return <LoadingState label="Загружаем карточки" />;
  if (!cards.data) return <ErrorState error={cards.error} onRetry={() => void cards.refetch()} />;

  return (
    <div className="page">
      <ViewHeader
        title="Карточки"
        fetching={cards.isFetching}
        updatedAt={cards.dataUpdatedAt}
        onRefresh={() => void cards.refetch()}
      />
      <div className="view-toolbar">
        <p>
          Карточки-брифы из knowledge/cards каждого репозитория. Источник правды — git:
          здесь только просмотр, правки идут через задачи или PR.
        </p>
      </div>
      {grouped.length === 0 ? (
        <EmptyState
          icon={<FileText size={22} />}
          title="Карточек не найдено"
          description="В подключённых репозиториях нет knowledge/cards, либо GitHub недоступен."
        />
      ) : (
        grouped.map(([identity, list]) => (
          <section className="panel" key={identity}>
            <PanelHeading title={repoShort(identity)} aside={`${list.length} карточек · ${identity}`} />
            <div className="card-list">
              {list.map((card) => (
                <button className="card-row" key={card.path} onClick={() => setSelected(card)}>
                  <span className="card-identity">
                    <strong>{card.name}</strong>
                    {card.next_action && <small>Далее: {card.next_action}</small>}
                  </span>
                  <span className={`status-badge ${statusTone(card.status)}`}>
                    <span className="status-dot" />
                    {card.status ? card.status.slice(0, 60) : "нет статуса"}
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}

function CardDetail({ card, onBack }: { card: CardSummary; onBack: () => void }) {
  const content = useQuery({
    queryKey: ["card", card.repository_id, card.path],
    queryFn: () => api.cardContent(card.repository_id, card.path),
    staleTime: 60_000,
  });
  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Все карточки</button>
      <div className="detail-heading">
        <div>
          <span className={`status-badge ${statusTone(card.status)}`}>
            <span className="status-dot" />{card.status || "нет статуса"}
          </span>
          <h1>{card.name}</h1>
          <p>{card.repository_identity} · {(card.size / 1024).toFixed(1)} KiB</p>
        </div>
        <div className="detail-actions">
          <a className="button button-secondary" href={card.github_url} target="_blank" rel="noreferrer">
            <ExternalLink size={14} /> Открыть на GitHub
          </a>
        </div>
      </div>
      <section className="panel detail-main">
        <PanelHeading title="Содержимое" aside={card.path} />
        {content.isPending ? (
          <p className="muted"><LoaderCircle size={15} className="spin" /> Загрузка…</p>
        ) : content.data ? (
          <div className="long-copy card-content">{content.data.content}</div>
        ) : (
          <ErrorState error={content.error} onRetry={() => void content.refetch()} />
        )}
      </section>
    </div>
  );
}
