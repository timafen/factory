import { LoaderCircle, Save, Waypoints, ExternalLink } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { runtimeLabel } from "./format";
import type { PipelineConfig, Worker } from "./types";
import {
  ErrorState,
  InlineError,
  LoadingState,
  PanelHeading,
  ViewHeader,
} from "./ui";

const TIERS = ["low", "medium", "high"] as const;
const TIER_LABEL: Record<string, string> = {
  low: "Простая",
  medium: "Средняя",
  high: "Сложная",
};
const DECISION_MODELS = ["fable", "sonnet", "opus", "haiku"];

export function PipelineView({ onWorkflow }: { onWorkflow: (id: string) => void }) {
  const queryClient = useQueryClient();
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: api.pipeline });
  const workers = useQuery({ queryKey: ["workers"], queryFn: api.workers });
  const workflows = useQuery({ queryKey: ["workflows", "enabled"], queryFn: api.allEnabledWorkflows });

  const [draft, setDraft] = useState<PipelineConfig | null>(null);
  useEffect(() => {
    // Seed the editable copy only when the asynchronously loaded config arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (pipeline.data && !draft) setDraft(structuredClone(pipeline.data));
  }, [pipeline.data, draft]);

  const save = useMutation({
    mutationFn: (config: PipelineConfig) => api.savePipeline(config),
    onSuccess: (saved) => {
      queryClient.setQueryData(["pipeline"], saved);
      setDraft(structuredClone(saved));
    },
  });

  const workflowIdByTitle = useMemo(() => {
    const map = new Map<string, string>();
    for (const wf of workflows.data ?? []) map.set(wf.current_revision.title, wf.id);
    return map;
  }, [workflows.data]);

  if (pipeline.isPending) return <LoadingState label="Загружаем конвейер" />;
  if (!pipeline.data) return <ErrorState error={pipeline.error} onRetry={() => void pipeline.refetch()} />;
  if (!draft) return <LoadingState label="Загружаем конвейер" />;

  const workerNames = (workers.data ?? []).map((w: Worker) => w.name).sort();
  const dirty = JSON.stringify(draft) !== JSON.stringify(pipeline.data);

  const setStageWorker = (index: number, tier: string, worker: string) => {
    setDraft((cur) => {
      if (!cur) return cur;
      const next = structuredClone(cur);
      const stage = next.stages[index];
      const workersMap = { ...(stage.workers ?? {}) };
      if (stage.worker && !stage.workers) {
        for (const t of TIERS) workersMap[t] = stage.worker;
      }
      workersMap[tier] = worker;
      stage.workers = workersMap;
      delete stage.worker;
      return next;
    });
  };

  const tierValue = (stage: PipelineConfig["stages"][number], tier: string) =>
    stage.workers?.[tier] ?? stage.worker ?? "";

  return (
    <div className="page">
      <ViewHeader
        title="Конвейер"
        fetching={pipeline.isFetching}
        updatedAt={pipeline.dataUpdatedAt}
        onRefresh={() => {
          setDraft(null);
          void pipeline.refetch();
        }}
      />
      <div className="view-toolbar">
        <p>Порядок шагов конвейера и модель для каждого шага по сложности. Инструкции шагов правятся в сценариях.</p>
        <button
          className="button button-primary"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(draft)}
        >
          {save.isPending ? <><LoaderCircle size={15} className="spin" /> Сохранение…</> : <><Save size={15} /> Сохранить</>}
        </button>
      </div>
      {save.error && <InlineError error={save.error} />}

      <section className="panel">
        <PanelHeading title="Автоматический режим" />
        <div className="detail-grid">
          <div className="field">
            <label htmlFor="pipe-enabled">Оркестратор</label>
            <select
              id="pipe-enabled"
              value={draft.enabled ? "on" : "off"}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.value === "on" })}
            >
              <option value="on">Включён — ведёт [auto]-задачи по шагам</option>
              <option value="off">Выключен — только ручной запуск</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="pipe-decision">Модель-оркестратор (решает: дальше / стоп + сложность)</label>
            <select
              id="pipe-decision"
              value={draft.decision_model}
              onChange={(e) => setDraft({ ...draft, decision_model: e.target.value })}
            >
              {[...new Set([...DECISION_MODELS, draft.decision_model])].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section className="panel">
        <PanelHeading title="Шаги" aside={`${draft.stages.length} шт. · выполняются по порядку`} />
        <div className="pipeline-stages">
          {draft.stages.map((stage, index) => {
            const wfId = workflowIdByTitle.get(stage.workflow);
            return (
              <div className="pipeline-stage" key={index}>
                <div className="pipeline-stage-head">
                  <span className="pipeline-step-badge">{index + 1}</span>
                  <strong>{stage.workflow}</strong>
                  {wfId ? (
                    <button className="button button-secondary button-sm" onClick={() => onWorkflow(wfId)}>
                      <ExternalLink size={13} /> Инструкция
                    </button>
                  ) : (
                    <span className="field-hint">нет сценария с таким названием</span>
                  )}
                </div>
                <div className="pipeline-tiers">
                  {TIERS.map((tier) => (
                    <div className="field" key={tier}>
                      <label htmlFor={`stage-${index}-${tier}`}>{TIER_LABEL[tier]}</label>
                      <select
                        id={`stage-${index}-${tier}`}
                        value={tierValue(stage, tier)}
                        onChange={(e) => setStageWorker(index, tier, e.target.value)}
                      >
                        <option value="">— выбрать воркер —</option>
                        {workerNames.map((name) => {
                          const w = (workers.data ?? []).find((x) => x.name === name);
                          return (
                            <option key={name} value={name}>
                              {name}{w ? ` · ${runtimeLabel(w.runtime)}` : ""}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel">
        <PanelHeading title="Как это работает" />
        <div className="long-copy">
          Оркестратор оценивает результат каждого шага и выбирает сложность следующего (простая / средняя / сложная),
          затем берёт для него соответствующий воркер отсюда. Так простые шаги идут на дешёвых моделях, а тяжёлые — на сильных.
          Тексты инструкций каждого шага — в разделе «Сценарии»; изменения применяются со следующей задачи.
        </div>
      </section>
    </div>
  );
}

// icon export so App can reference the same glyph
export const PipelineIcon = Waypoints;
