import { CheckCircle2, LoaderCircle, ShieldCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { APIError } from "./api";
import { InlineError, PanelHeading } from "./ui";

type Command = { argv: string[] };
type OnboardingInput = {
  project_id: string;
  name: string;
  default_branch: string;
  allowed_paths: string[];
  required_instruction_files: string[];
  commands: { working_directory: string; install: Command; test: Command; build: Command };
  timeout_seconds: number;
  runtime: { os: string; architecture: string; toolchain: string; toolchain_version: string };
  environment: { network: "NONE"; secrets: "NONE" };
  policy: { write: "NONE"; pull_request: "DISABLED"; release: "DISABLED" };
};
type OnboardingCard = OnboardingInput & {
  repository_id: string;
  remote_identity: string;
  enabled: false;
  discovered_instruction_files?: string[];
  readiness_state?: string;
  readiness_reason?: string;
};
type FormDraft = {
  projectID: string;
  name: string;
  branch: string;
  allowedPaths: string;
  instructions: string;
  workingDirectory: string;
  install: string;
  test: string;
  build: string;
  timeout: number;
};

async function onboardingRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!response.ok) {
    let body: { error?: { code?: string; message?: string } } | undefined;
    try { body = await response.json() as typeof body; } catch { /* proxy returned no JSON */ }
    throw new APIError(body?.error?.code ?? "request_failed", body?.error?.message ?? `Request failed with status ${response.status}`, response.status);
  }
  return await response.json() as T;
}

function splitList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseArgv(value: string, label: string): string[] {
  if (!value.trim()) return [];
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== "string")) {
    throw new Error(`${label} must be a JSON array of strings.`);
  }
  return parsed;
}

function defaultIdentity(remoteIdentity: string) {
  const repository = remoteIdentity.split("/").at(-1) ?? "project";
  if (repository === "timstruck_laravel") return { id: "timstruck", name: "Timstruck.net", branch: "master" };
  if (repository === "tarser-operations") return { id: "tarser", name: "Tarser", branch: "main" };
  if (repository === "assistant") return { id: "timofey-assistant", name: "Timofey Assistant", branch: "main" };
  return { id: repository.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""), name: repository, branch: "main" };
}

export function ProjectOnboardingPanel({ repositoryID, remoteIdentity, repositoryEnabled }: {
  repositoryID: string;
  remoteIdentity: string;
  repositoryEnabled: boolean;
}) {
  const defaults = defaultIdentity(remoteIdentity);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["project-onboarding", repositoryID],
    queryFn: async () => {
      try {
        return await onboardingRequest<OnboardingCard>(`/api/v1/repositories/${encodeURIComponent(repositoryID)}/onboarding`);
      } catch (error) {
        if (error instanceof APIError && error.status === 404) return null;
        throw error;
      }
    },
    retry: false,
  });
  const [draft, setDraft] = useState<Partial<FormDraft>>({});
  const [formError, setFormError] = useState<Error | null>(null);
  const card = query.data;
  const projectID = draft.projectID ?? card?.project_id ?? defaults.id;
  const name = draft.name ?? card?.name ?? defaults.name;
  const branch = draft.branch ?? card?.default_branch ?? defaults.branch;
  const allowedPaths = draft.allowedPaths ?? card?.allowed_paths.join(", ") ?? "docs";
  const instructions = draft.instructions ?? card?.required_instruction_files.join(", ") ?? "";
  const workingDirectory = draft.workingDirectory ?? card?.commands.working_directory ?? "";
  const install = draft.install ?? JSON.stringify(card?.commands.install.argv ?? []);
  const test = draft.test ?? JSON.stringify(card?.commands.test.argv ?? ["git", "diff", "--check"]);
  const build = draft.build ?? JSON.stringify(card?.commands.build.argv ?? []);
  const timeout = draft.timeout ?? card?.timeout_seconds ?? 120;

  const save = useMutation({
    mutationFn: async () => {
      const input: OnboardingInput = {
        project_id: projectID.trim(), name: name.trim(), default_branch: branch.trim(),
        allowed_paths: splitList(allowedPaths), required_instruction_files: splitList(instructions),
        commands: {
          working_directory: workingDirectory.trim(),
          install: { argv: parseArgv(install, "Install command") },
          test: { argv: parseArgv(test, "Test command") },
          build: { argv: parseArgv(build, "Build command") },
        },
        timeout_seconds: timeout,
        runtime: { os: "linux", architecture: "amd64", toolchain: "git", toolchain_version: "2" },
        environment: { network: "NONE", secrets: "NONE" },
        policy: { write: "NONE", pull_request: "DISABLED", release: "DISABLED" },
      };
      return onboardingRequest<OnboardingCard>(`/api/v1/repositories/${encodeURIComponent(repositoryID)}/onboarding`, { method: "PUT", body: JSON.stringify(input) });
    },
    onSuccess: (card) => {
      setFormError(null);
      setDraft({});
      queryClient.setQueryData(["project-onboarding", repositoryID], card);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      parseArgv(install, "Install command");
      parseArgv(test, "Test command");
      parseArgv(build, "Build command");
      setFormError(null);
      save.mutate();
    } catch (error) {
      setFormError(error instanceof Error ? error : new Error("Commands are invalid."));
    }
  };
  return (
    <section className="panel" aria-labelledby="project-onboarding-title">
      <PanelHeading title="Project onboarding" aside={card ? "Disabled card saved" : "Not configured"} />
      <div id="project-onboarding-title" className="quiet-empty">
        Save the inert project contract while repository routing is disabled. Doctor and trial execution are not enabled in this slice.
      </div>
      {repositoryEnabled && <div className="repository-duplicate" role="alert">Disable repository routing before first acceptance.</div>}
      <form className="automation-form-grid" onSubmit={submit}>
        <div className="field"><label htmlFor="onboarding-project-id">Project ID</label><input id="onboarding-project-id" value={projectID} onChange={(event) => setDraft((current) => ({ ...current, projectID: event.target.value }))} /></div>
        <div className="field"><label htmlFor="onboarding-name">Name</label><input id="onboarding-name" value={name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></div>
        <div className="field"><label htmlFor="onboarding-branch">Default branch</label><input id="onboarding-branch" value={branch} onChange={(event) => setDraft((current) => ({ ...current, branch: event.target.value }))} /></div>
        <div className="field"><label htmlFor="onboarding-timeout">Timeout seconds</label><input id="onboarding-timeout" type="number" min={1} max={1800} value={timeout} onChange={(event) => setDraft((current) => ({ ...current, timeout: Number(event.target.value) }))} /></div>
        <div className="field"><label htmlFor="onboarding-paths">Allowed paths</label><input id="onboarding-paths" value={allowedPaths} onChange={(event) => setDraft((current) => ({ ...current, allowedPaths: event.target.value }))} placeholder="docs, README.md" /></div>
        <div className="field"><label htmlFor="onboarding-instructions">Required instruction files</label><input id="onboarding-instructions" value={instructions} onChange={(event) => setDraft((current) => ({ ...current, instructions: event.target.value }))} placeholder="AGENTS.md" /></div>
        <div className="field"><label htmlFor="onboarding-directory">Working directory</label><input id="onboarding-directory" value={workingDirectory} onChange={(event) => setDraft((current) => ({ ...current, workingDirectory: event.target.value }))} placeholder="blank for repository root" /></div>
        <div className="field"><label htmlFor="onboarding-install">Install argv</label><input id="onboarding-install" value={install} onChange={(event) => setDraft((current) => ({ ...current, install: event.target.value }))} spellCheck={false} /></div>
        <div className="field"><label htmlFor="onboarding-test">Test argv</label><input id="onboarding-test" value={test} onChange={(event) => setDraft((current) => ({ ...current, test: event.target.value }))} spellCheck={false} /></div>
        <div className="field"><label htmlFor="onboarding-build">Build argv</label><input id="onboarding-build" value={build} onChange={(event) => setDraft((current) => ({ ...current, build: event.target.value }))} spellCheck={false} /></div>
        <div className="field"><label>Fixed safety envelope</label><span className="field-hint"><ShieldCheck size={13} /> Network NONE · secrets NONE · write NONE · PR/release disabled</span></div>
        <button className="button button-primary" type="submit" disabled={save.isPending || repositoryEnabled}>{save.isPending ? <LoaderCircle size={15} className="spin" /> : <CheckCircle2 size={15} />} Save disabled card</button>
      </form>
      <InlineError error={formError ?? save.error ?? query.error} />
      {card && <p className="field-hint">Card enabled: no · discovered rules: unset · readiness: unset · receipts: unset</p>}
    </section>
  );
}
