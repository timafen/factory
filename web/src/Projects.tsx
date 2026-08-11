import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, LockKeyhole, ShieldCheck, XCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "./api";
import type { CreateProjectInput, Project, ProjectType } from "./types";
import { EmptyState, ErrorState, InlineError, LoadingState, PanelHeading, StaleBanner, ViewHeader } from "./ui";

const policies: Record<ProjectType, { remote: string; url: string; health: string; release: string; rollback: string }> = {
  "factory-single-instance": { remote: "github.com/timafen/factory", url: "https://factory.timafen.com", health: "https://factory.timafen.com/api/v1/dashboard", release: "fx-factory-release", rollback: "fx-factory-rollback" },
  "tarser-operations-staging": { remote: "github.com/timafen/tarser-operations", url: "https://staging-automation.tarser.net", health: "https://staging-automation.tarser.net/ops/health/", release: "tarser-staging-deploy-release", rollback: "tarser-staging-auto-rollback" },
};

function ProjectCard({ project }: { project: Project }) {
  const readiness = useQuery({ queryKey: ["project-readiness", project.id], queryFn: () => api.projectReadiness(project.id) });
  const [commitSHA, setCommitSHA] = useState("");
  const operation = useMutation({ mutationFn: (kind: "release" | "rollback") => api.runProjectOperation(project.id, "staging", kind, commitSHA) });
  return <article className="panel project-card">
    <div className="project-card-heading"><div><span className={`status-badge ${readiness.data?.ready ? "success" : "warning"}`}>{readiness.data?.ready ? "Готов" : "Закрыт"}</span><h2>{project.name}</h2></div><code>{project.project_type}</code></div>
    <p className="break-anywhere">{project.remote_identity} · ветка {project.main_branch}</p>
    <dl className="metadata compact-metadata">
      <div><dt>Исполнитель</dt><dd>{project.executor_group}</dd></div><div><dt>Среда</dt><dd>{project.environments[0]?.url}</dd></div>
      <div><dt>Выпуск</dt><dd>{project.environments[0]?.release_adapter}</dd></div><div><dt>Возврат</dt><dd>{project.environments[0]?.rollback_adapter}</dd></div>
    </dl>
    {readiness.error && <InlineError error={readiness.error} />}
    <div className="project-gates" aria-label={`Готовность ${project.name}`}>
      {(readiness.data?.gates ?? []).map((gate) => <span key={gate.name} title={gate.reason}>{gate.ready ? <CheckCircle2 size={14} /> : <XCircle size={14} />}{gate.name}</span>)}
      {(readiness.data?.secrets ?? []).map((secret) => <span key={secret.name} title="Показывается только наличие, не значение"><LockKeyhole size={14} />{secret.name}: {secret.present ? "есть" : "нет"}</span>)}
    </div>
    <div className="project-operation">
      <label className="field">Проверенный SHA<input aria-label={`Проверенный SHA ${project.name}`} value={commitSHA} onChange={(event) => setCommitSHA(event.target.value)} placeholder={readiness.data?.commit_sha ?? "40-символьный SHA"} /></label>
      <button className="button button-primary" disabled={!readiness.data?.ready || !commitSHA || operation.isPending} onClick={() => operation.mutate("release")}>Выпустить staging</button>
      <button className="button button-secondary" disabled={!readiness.data?.ready || !commitSHA || operation.isPending} onClick={() => operation.mutate("rollback")}>Вернуть staging</button>
    </div>
    {operation.error && <InlineError error={operation.error} />}{operation.data && <p className="operation-status" role="status">{operation.data.message}</p>}
  </article>;
}

export function ProjectsView() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [name, setName] = useState(""); const [type, setType] = useState<ProjectType>("factory-single-instance"); const [branch, setBranch] = useState("main"); const [secrets, setSecrets] = useState("GITHUB_TOKEN");
  const policy = policies[type];
  const create = useMutation({ mutationFn: () => {
    const input: CreateProjectInput = { name, remote_identity: policy.remote, main_branch: branch, project_type: type, required_checks: ["secret-scan", "static-typecheck", "tests", "build"], environments: [{ name: "staging", url: policy.url, health_url: policy.health, blocked: false, release_adapter: policy.release, rollback_adapter: policy.rollback, required_secrets: secrets.split(",").map((value) => value.trim()).filter(Boolean), web_hosts: [new URL(policy.url).hostname] }] };
    return api.createProject(input);
  }, onSuccess: ({ project }) => { queryClient.setQueryData<Project[]>(["projects"], (current) => [...(current ?? []).filter((item) => item.id !== project.id), project]); setName(""); } });
  const submit = (event: FormEvent) => { event.preventDefault(); if (name.trim() && branch.trim() && secrets.trim()) create.mutate(); };
  if (projects.isPending) return <LoadingState label="Загрузка проектов" />;
  if (!projects.data) return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;
  return <div className="page projects-page">
    <ViewHeader title="Безопасные проекты" fetching={projects.isFetching} updatedAt={projects.dataUpdatedAt} onRefresh={() => void projects.refetch()} />
    {projects.error && <StaleBanner error={projects.error} />}
    <section className="panel project-create-panel"><PanelHeading title="Подключить по безопасному шаблону" aside="Только staging в v1" />
      <form className="project-create-form" onSubmit={submit}>
        <label className="field">Название<input aria-label="Название проекта" value={name} onChange={(event) => setName(event.target.value)} required /></label>
        <label className="field">Тип<select aria-label="Тип проекта" value={type} onChange={(event) => setType(event.target.value as ProjectType)}><option value="factory-single-instance">Factory, один экземпляр</option><option value="tarser-operations-staging">Tarser, только staging</option></select></label>
        <label className="field">Основная ветка<input aria-label="Основная ветка" value={branch} onChange={(event) => setBranch(event.target.value)} required /></label>
        <label className="field">Имена секретов<input aria-label="Имена секретов" value={secrets} onChange={(event) => setSecrets(event.target.value)} required /></label>
        <div className="project-policy-summary"><ShieldCheck size={18} /><span>Репозиторий, группа, хост и адаптеры закреплены сервером.<br /><code>{policy.remote}</code></span></div>
        <button className="button button-primary" disabled={create.isPending}>{create.isPending ? "Подключение…" : "Подключить проект"}</button>
      </form>{create.error && <InlineError error={create.error} />}
    </section>
    {projects.data.length === 0 ? <EmptyState icon={<ShieldCheck size={22} />} title="Проектов пока нет" description="Подключите Factory или staging Tarser через проверяемый шаблон." /> : <div className="projects-grid">{projects.data.map((project) => <ProjectCard key={project.id} project={project} />)}</div>}
  </div>;
}
