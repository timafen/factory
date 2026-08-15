import { AlertCircle, LoaderCircle, Plus, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api } from "./api";
import { invalidateControlPlane } from "./controlPlaneQueries";
import { runtimeLabel } from "./format";
import { TaskFilePicker } from "./TaskFilePicker";
import type { CreateTaskInput, Worker } from "./types";
import { InlineError } from "./ui";

export function DelegateModal({
  workers,
  workersPending,
  initialWorkerID,
  onClose,
  onCreated,
}: {
  workers: Worker[];
  workersPending: boolean;
  initialWorkerID?: string;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  // Порядок стадий конвейера и человеческие названия. Держим здесь же,
  // чтобы заголовок задачи собирался ровно так, как его читает пилот.
  const PIPELINE = [
    { wf: "Triage", ru: "Разбор" },
    { wf: "Specification", ru: "Спецификация" },
    { wf: "Implement + Test", ru: "Разработка" },
    { wf: "Review", ru: "Ревью" },
    { wf: "Verify", ru: "Проверка" },
  ];
  const queryClient = useQueryClient();
  const titleID = useId();
  const descriptionID = useId();
  const workflowID = useId();
  const titleRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<{ fingerprint: string; key: string } | undefined>(undefined);
  const [workerID, setWorkerID] = useState(initialWorkerID ?? "");
  const [repositoryID, setRepositoryID] = useState("");
  const [timeout, setTimeout] = useState("7200");
  const [workflowRevisionID, setWorkflowRevisionID] = useState("");
  const [mode, setMode] = useState<"manual" | "auto">("manual");
  const [startStage, setStartStage] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
	const [visual, setVisual] = useState(false);
  const selectedWorker = workers.find((worker) => worker.id === workerID);
  const repositoryOptions = useQuery({
    queryKey: ["worker-repository-options", workerID],
    queryFn: () => api.workerRepositoryOptions(workerID),
    enabled: Boolean(workerID),
  });
  const repositories = repositoryOptions.data ?? [];
  const workflows = useQuery({
    queryKey: ["workflows", "enabled"],
    queryFn: api.allEnabledWorkflows,
  });

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const focusable = [...(modalRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [])];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && (document.activeElement === first || !modalRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const create = useMutation({
    mutationFn: api.createTask,
    onSuccess: async (detail) => {
      await invalidateControlPlane(queryClient);
      onCreated(detail.task.id);
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isSubmitting) return;
    const form = new FormData(event.currentTarget);
    const rawTitle = String(form.get("title") ?? "").trim();
    const cleanedTitle = rawTitle.replace(/^\[auto\]\s*/i, "");
    const stageTag = mode === "auto" && startStage > 0
      ? `[${startStage + 1}/${PIPELINE.length} ${PIPELINE[startStage].wf}] `
      : "";
    const title = mode === "auto" ? `[auto] ${stageTag}${cleanedTitle}` : cleanedTitle;
    const context = String(form.get("description") ?? "");
    const nextErrors: Record<string, string> = {};
    if (!cleanedTitle) nextErrors.title = "Введите название задачи.";
    else if (Array.from(title).length > 200) nextErrors.title = "Название не должно быть длиннее 200 символов.";
    if (!context.trim()) nextErrors.description = "Введите контекст задачи.";
    if (!workerID) nextErrors.worker = "Выберите исполнителя.";
    if (!repositoryID) nextErrors.repository = "Выберите репозиторий.";
	const visualURL = String(form.get("visual_url") ?? "").trim();
	const visualState = String(form.get("visual_state") ?? "").trim();
	const viewportWidth = Number(form.get("viewport_width"));
	const viewportHeight = Number(form.get("viewport_height"));
	if (visual && (!visualURL || !visualState || viewportWidth < 320 || viewportWidth > 2560 || viewportHeight < 320 || viewportHeight > 2560)) nextErrors.visual = "Укажите URL, точный текст и viewport от 320 до 2560 px.";
    const timeoutSeconds = Number(timeout);
    if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 28_800) {
      nextErrors.timeout = "Выберите время от одной минуты до восьми часов.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    const selectedRepository = repositories.find((repository) => repository.id === repositoryID);
    const assignment = selectedRepository && !selectedRepository.advertised
      ? {
          route: {
            repository_remote_identity: selectedRepository.remote_identity,
            source_access: { provider: "github", hostname: "github.com" },
          },
        }
      : { repository_id: repositoryID };
    const payload = {
      title,
      worker_id: workerID,
      ...assignment,
      timeout_seconds: timeoutSeconds,
      ...(workflowRevisionID
        ? { context, workflow_revision_id: workflowRevisionID }
        : { description: context }),
	  ...(visual ? { visual_target: { url: visualURL, state_text: visualState, viewport_width: viewportWidth, viewport_height: viewportHeight, after_workflow_title: mode === "auto" ? "Verify" : "" } } : {}),
    };
    const fingerprint = JSON.stringify(payload);
    if (requestRef.current?.fingerprint !== fingerprint) {
      requestRef.current = { fingerprint, key: crypto.randomUUID() };
    }
    const input = {
      request_key: requestRef.current.key,
      ...payload,
    } as CreateTaskInput;
	void (async () => {
		const attachments = [];
		let creatingTask = false;
		setIsSubmitting(true);
		try {
			for (const file of attachmentFiles) attachments.push(await api.uploadTaskAttachment(input.request_key, file));
			creatingTask = true;
			await create.mutateAsync({ ...input, attachment_ids: attachments.map((item) => item.id) });
		} catch (error) {
			await Promise.allSettled(attachments.map((item) => api.deleteTaskAttachment(input.request_key,item.id)));
			if (!creatingTask) setErrors((current) => ({ ...current, attachments: error instanceof Error ? error.message : "Не удалось загрузить вложения." }));
		} finally {
			setIsSubmitting(false);
		}
	})();
  };

  return (
    <div className="modal-layer">
      <button className="modal-scrim" aria-label="Закрыть постановку задачи" onClick={onClose} />
      <div ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="delegate-heading">
        <div className="modal-header">
          <div>
            <h2 id="delegate-heading">Поставить задачу</h2>
          </div>
          <button className="icon-button" aria-label="Закрыть" onClick={onClose}><X size={19} /></button>
        </div>
        <form onSubmit={submit} noValidate>
          <div className="modal-body">
            <Field label="Название" htmlFor={titleID} error={errors.title}>
              <input ref={titleRef} id={titleID} name="title" aria-invalid={Boolean(errors.title)} placeholder="Исправить устаревший статус исполнителя" />
            </Field>
            <Field
              label="Режим"
              htmlFor="delegate-mode"
              hint={mode === "auto"
                ? "Автоматический: пилот проведёт задачу по шагам конвейера и выберет модель для каждого шага. К названию добавится [auto]."
                : "Ручной: на выбранном исполнителе выполнится только этот шаг. Следующие шаги задаёте вы."}
            >
              <select id="delegate-mode" value={mode} onChange={(event) => setMode(event.target.value as "manual" | "auto")}>
                <option value="manual">Ручной — выполнить только этот шаг</option>
                <option value="auto">Автоматический — пилот пройдёт весь конвейер</option>
              </select>
            </Field>
            {mode === "auto" && (
              <Field
                label="С какого шага начать"
                htmlFor="delegate-start-stage"
                hint={startStage === 0
                  ? "С начала: конвейер сам разберёт задачу и напишет спецификацию."
                  : `Шаги ${PIPELINE.slice(0, startStage).map((p) => p.ru).join(", ")} будут помечены как не нужные — считаем, что ты сделал их сам. Не забудь описать задачу подробно в контексте.`}
              >
                <select
                  id="delegate-start-stage"
                  value={startStage}
                  onChange={(event) => {
                    const i = Number(event.target.value);
                    setStartStage(i);
                    const wanted = PIPELINE[i].wf;
                    const wf = (workflows.data ?? []).find(
                      (w) => w.current_revision.title === wanted);
                    if (wf) setWorkflowRevisionID(wf.current_revision.id);
                  }}
                >
                  {PIPELINE.map((p, i) => (
                    <option key={p.wf} value={i}>
                      {i === 0 ? `С начала — ${p.ru}` : `Сразу с шага ${i + 1} — ${p.ru}`}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <Field
              label="Сценарий"
              htmlFor={workflowID}
              hint="Без сценария контекст станет полной инструкцией."
            >
              <select
                id={workflowID}
                value={workflowRevisionID}
                onChange={(event) => setWorkflowRevisionID(event.target.value)}
                disabled={workflows.isPending}
              >
                <option value="">Без сценария</option>
                {(workflows.data ?? []).map((workflow) => (
                  <option key={workflow.id} value={workflow.current_revision.id}>
                    {workflow.current_revision.title} · revision {workflow.current_revision.revision_number}
                  </option>
                ))}
              </select>
            </Field>
            {workflows.error && <InlineError error={workflows.error} />}
            <Field
              label="Контекст"
              htmlFor={descriptionID}
              error={errors.description}
              hint={selectedWorker
                ? workflowRevisionID
                  ? `Factory объединит это с выбранным сценарием для ${runtimeLabel(selectedWorker.runtime)}.`
                  : `Это станет инструкцией для ${runtimeLabel(selectedWorker.runtime)}.`
                : workflowRevisionID
                  ? "Factory объединит это с выбранным сценарием."
                  : "Это станет инструкцией для выбранного исполнителя."}
            >
              <textarea id={descriptionID} name="description" rows={6} aria-invalid={Boolean(errors.description)} placeholder="Опишите результат, ограничения и проверки…" />
            </Field>
            <Field label="Файлы" htmlFor="task-files">
              <TaskFilePicker files={attachmentFiles} onChange={setAttachmentFiles} error={errors.attachments} />
            </Field>
			<label className="checkbox-row"><input type="checkbox" checked={visual} onChange={event => setVisual(event.target.checked)} /> Меняется видимый экран</label>
			{visual && <div className="visual-target-fields">
			  <Field label="URL экрана" htmlFor="visual-url" error={errors.visual}><input id="visual-url" name="visual_url" type="url" placeholder="https://staging.example/listings" /></Field>
			  <Field label="Точный видимый текст" htmlFor="visual-state"><input id="visual-state" name="visual_state" placeholder="Объявления готовы" /></Field>
			  <Field label="Ширина" htmlFor="viewport-width"><input id="viewport-width" name="viewport_width" type="number" min="320" max="2560" defaultValue="1280" /></Field>
			  <Field label="Высота" htmlFor="viewport-height"><input id="viewport-height" name="viewport_height" type="number" min="320" max="2560" defaultValue="720" /></Field>
			</div>}
            <Field label="Исполнитель" htmlFor="delegate-worker" error={errors.worker}>
              <select
                id="delegate-worker"
                value={workerID}
                onChange={(event) => {
                  setWorkerID(event.target.value);
                  setRepositoryID("");
                }}
                disabled={workersPending || workers.length === 0}
              >
                <option value="">{workersPending ? "Загружаем исполнителей…" : workers.length ? "Выберите исполнителя" : "Исполнители не зарегистрированы"}</option>
                {workers.map((worker) => (
                  <option key={worker.id} value={worker.id}>
                    {worker.name} · {runtimeLabel(worker.runtime)} · {worker.online ? "в сети" : "не в сети"}
                  </option>
                ))}
              </select>
            </Field>
            {selectedWorker && !selectedWorker.online && (
              <div className="warning-banner compact"><AlertCircle size={16} /> Исполнитель не в сети. Задача будет ждать в очереди.</div>
            )}
            {selectedWorker?.health === "unhealthy" && (
              <div className="warning-banner compact"><AlertCircle size={16} /> Исполнитель недоступен и не возьмёт задачу, пока не восстановится.</div>
            )}
            <Field label="Репозиторий" htmlFor="delegate-repository" error={errors.repository}>
              <select id="delegate-repository" value={repositoryID} onChange={(event) => setRepositoryID(event.target.value)} disabled={!workerID || repositoryOptions.isPending}>
                <option value="">{!workerID ? "Сначала выберите исполнителя" : repositoryOptions.isPending ? "Загружаем репозитории…" : repositories.length ? "Выберите репозиторий" : "Нет доступных репозиториев"}</option>
                {repositories.map((repo) => <option key={repo.id} value={repo.id} disabled={!repo.ready && !repo.advertised}>{repo.key ? `${repo.key} · ` : ""}{repo.remote_identity}{repo.ready && !repo.advertised ? " · acquired on demand" : ""}{!repo.ready ? ` · ${repo.reason}` : ""}</option>)}
              </select>
            </Field>
            {repositoryOptions.error && <InlineError error={repositoryOptions.error} />}
            <Field label="Время выполнения" htmlFor="delegate-timeout" error={errors.timeout}>
              <select id="delegate-timeout" value={timeout} onChange={(event) => setTimeout(event.target.value)}>
                <option value="1800">30 минут</option>
                <option value="3600">1 час</option>
                <option value="7200">2 часа</option>
                <option value="14400">4 часа</option>
                <option value="28800">8 часов</option>
              </select>
            </Field>
            {create.error && <InlineError error={create.error} />}
          </div>
          <div className="modal-footer">
            <button type="button" className="button button-secondary" onClick={onClose}>Отмена</button>
            <button type="submit" className="button button-primary" disabled={isSubmitting || workers.length === 0}>
              {isSubmitting ? <><LoaderCircle size={16} className="spin" /> Ставим задачу…</> : <><Plus size={16} /> Поставить задачу</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <span className="field-error">{error}</span> : hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}
