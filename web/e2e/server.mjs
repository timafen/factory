import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer as createHTTPSServer } from "node:https";
import { request as proxyRequest } from "node:http";

const root = resolve(import.meta.dirname, "../..");
const temporary = await mkdtemp(join(tmpdir(), "factory-ui-e2e-"));
const serverBinary = join(temporary, "factory-server");
const workerBinary = join(temporary, "factory-worker");
const database = join(temporary, "server", "factory.sqlite3");
const workerData = join(temporary, "worker");
const workerConfig = join(temporary, "worker.toml");
const fakeBin = join(temporary, "bin");
const legacyRoot = resolve(import.meta.dirname, "../test-results/legacy-poller");
const legacyConfig = join(legacyRoot, "poller.toml");
const legacyLedger = join(legacyRoot, "poller", "poller.sqlite3");
const workerID = "11111111-1111-4111-8111-111111111111";
const workerBootstrapCredential = process.env.FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL;
const e2ePortValue = process.env.FACTORY_E2E_PORT;
const e2eBackendPortValue = process.env.FACTORY_E2E_BACKEND_PORT;
const pausedHTTPSWork = "HTTPS proxy resumes paused work";
const completedHTTPSWork = "HTTPS proxy clears completed pause";

if (!workerBootstrapCredential) {
  throw new Error("FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL is required");
}
if (!e2ePortValue || !/^[0-9]+$/.test(e2ePortValue)) {
  throw new Error("FACTORY_E2E_PORT must be an integer from 1 to 65535");
}
const e2ePort = Number(e2ePortValue);
if (!Number.isSafeInteger(e2ePort) || e2ePort < 1 || e2ePort > 65_535) {
  throw new Error("FACTORY_E2E_PORT must be an integer from 1 to 65535");
}
if (!e2eBackendPortValue || !/^[0-9]+$/.test(e2eBackendPortValue)) {
  throw new Error("FACTORY_E2E_BACKEND_PORT must be an integer from 1 to 65535");
}
const e2eBackendPort = Number(e2eBackendPortValue);
if (!Number.isSafeInteger(e2eBackendPort) || e2eBackendPort < 1 || e2eBackendPort > 65_535 || e2eBackendPort === e2ePort) {
  throw new Error("FACTORY_E2E_BACKEND_PORT must be a distinct integer from 1 to 65535");
}
const e2eProxyAddress = `127.0.0.1:${e2ePort}`;
const e2eServerAddress = `127.0.0.1:${e2eBackendPort}`;
const e2eServerOrigin = `http://${e2eServerAddress}`;

function run(command, args, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      cwd: options.cwd ?? root,
      env: options.env ?? process.env,
      stdio: options.stdio ?? "inherit",
    });
    child.once("error", rejectRun);
    child.once("exit", (code, signal) => {
      if (code === 0) resolveRun();
      else rejectRun(new Error(`${command} exited with ${code ?? signal}`));
    });
  });
}

async function createRepository(name) {
  const origin = join(temporary, `${name}-origin.git`);
  const checkout = join(temporary, name);
  await run("git", ["init", "--bare", "--initial-branch=main", origin]);
  await run("git", ["clone", origin, checkout]);
  await run("git", ["config", "user.name", "Factory browser test"], { cwd: checkout });
  await run("git", ["config", "user.email", "factory-browser@example.test"], { cwd: checkout });
  await writeFile(join(checkout, "README.md"), `# ${name}\n`);
  await run("git", ["add", "README.md"], { cwd: checkout });
  await run("git", ["commit", "-m", "test: initialize repository"], { cwd: checkout });
  await run("git", ["push", "--set-upstream", "origin", "main"], { cwd: checkout });
  return checkout;
}

async function createFakeCodex() {
  await mkdir(fakeBin, { recursive: true });
  const executable = join(fakeBin, "codex");
  await writeFile(
    executable,
    `#!/bin/sh
set -eu

if [ "\${1:-}" = "--version" ]; then
  echo "codex-cli 0.0.0-factory-e2e"
  exit 0
fi

if [ "\${1:-}" = "login" ] && [ "\${2:-}" = "status" ]; then
  echo "Logged in for deterministic Factory browser tests"
  exit 0
fi

if [ "\${1:-}" != "exec" ]; then
  echo "unexpected fake Codex arguments: $*" >&2
  exit 2
fi

result_path=
previous=
for argument in "$@"; do
  if [ "$previous" = "--output-last-message" ]; then
    result_path=$argument
    break
  fi
  previous=$argument
done
if [ -z "$result_path" ]; then
  echo "fake Codex did not receive --output-last-message" >&2
  exit 2
fi

prompt=$(cat)
branch=$(git branch --show-current)
printf '%s\\n' '{"type":"progress","message":"Inspected the assigned repository."}'

case "$prompt" in
  *FACTORY_E2E_FAIL*)
    echo "Deterministic fake Codex failure." >&2
    exit 42
    ;;
  *FACTORY_E2E_WAIT*)
    printf '%s\\n' '{"type":"progress","message":"Waiting for operator cancellation."}'
    trap 'exit 143' TERM INT
    while :; do sleep 1; done
    ;;
esac

printf '%s\\n' "Created by the Factory browser proof." > factory-proof.txt
printf '%s\\n' '{"type":"progress","message":"Created deterministic worktree evidence."}'
{
  printf '%s\\n' "Completed by deterministic fake Codex."
  printf 'Branch: %s\\n' "$branch"
  printf 'Worktree: %s\\n' "$PWD"
} > "$result_path"
`,
  );
  await chmod(executable, 0o755);
}

async function createFakeGH() {
  await mkdir(fakeBin, { recursive: true });
  const executable = join(fakeBin, "gh");
  await writeFile(
    executable,
    `#!/bin/sh
set -eu

if [ "\${1:-}" = "auth" ] && [ "\${2:-}" = "status" ]; then
  echo "Logged in to github.com for deterministic Factory browser tests"
  exit 0
fi

if [ "\${1:-}" = "issue" ] && [ "\${2:-}" = "list" ]; then
  printf '%s\n' '[{"number":184,"title":"Typed Automation browser fixture","url":"https://github.com/example/automation-fixture/issues/184","state":"OPEN","labels":[{"id":"label-ready","name":"factory:ready","description":"","color":"ffffff"}]}]'
  exit 0
fi

if [ "\${1:-}" = "pr" ] && [ "\${2:-}" = "list" ]; then
  printf '%s\n' '[{"number":185,"title":"Typed pull-request Automation browser fixture","url":"https://github.com/example/automation-fixture/pull/185","state":"OPEN","isDraft":false,"baseRefName":"main","headRefOid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","labels":[{"id":"label-review","name":"factory:review","description":"","color":"ffffff"}]}]'
  exit 0
fi

echo "unexpected fake gh arguments: $*" >&2
exit 2
`,
  );
  await chmod(executable, 0o755);
}

async function createLegacyPollerFixture() {
  await rm(legacyRoot, { recursive: true, force: true });
  await mkdir(join(legacyRoot, "poller"), { recursive: true });
  await writeFile(
    legacyConfig,
    `server = ${JSON.stringify(e2eServerOrigin)}
poll_every = "30s"
data_directory = "poller"

[[queues]]
name = "browser-ready"
source = "github"
project = "example/automation-fixture"
status = "open"
labels = ["factory:ready"]
prompt = "Implement the issue and open a reviewed pull request."
timeout_seconds = 3600
`,
    { mode: 0o600 },
  );
  const queueID = createHash("sha256")
    .update(["browser-ready", "github", "example/automation-fixture"].join("\0"))
    .digest("hex")
    .slice(0, 48);
  const requestBody = JSON.stringify({
    request_key: "legacy-browser-request-187",
    title: "Work on github ticket #187",
    description: "Resume the exact imported browser migration request.",
    timeout_seconds: 3600,
    route: {
      repository_remote_identity: "github.com/example/automation-fixture",
      source_access: { provider: "github", hostname: "github.com" },
    },
  });
  const helper = join(temporary, "create-legacy-ledger.go");
  await writeFile(helper, `package main

import (
  "database/sql"
  "os"
  _ "modernc.org/sqlite"
)

func main() {
  database, err := sql.Open("sqlite", os.Args[1])
  if err != nil { panic(err) }
  defer database.Close()
  _, err = database.Exec(\`CREATE TABLE observations (
    queue_id TEXT NOT NULL,
    issue_key TEXT NOT NULL,
    request_key TEXT NOT NULL UNIQUE,
    request_json BLOB NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ('pending', 'submitted')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (queue_id, issue_key)
  );
  CREATE INDEX observations_pending ON observations(state, created_at, queue_id, issue_key);\`)
  if err != nil { panic(err) }
  _, err = database.Exec(\`INSERT INTO observations(
    queue_id, issue_key, request_key, request_json, task_id, state, created_at, updated_at
  ) VALUES (?, '#187', ?, ?, '', 'pending', 1, 1)\`, os.Args[2], os.Args[3], []byte(os.Args[4]))
  if err != nil { panic(err) }
}
`);
  await run("go", ["run", helper, legacyLedger, queueID, "legacy-browser-request-187", requestBody]);
}

await Promise.all([
  run("go", ["build", "-o", serverBinary, "./cmd/factory-server"]),
  run("go", ["build", "-o", workerBinary, "./cmd/factory-worker"]),
  createFakeCodex(),
  createFakeGH(),
  createLegacyPollerFixture(),
]);
const [factoryRepository, handbookRepository] = await Promise.all([
  createRepository("factory-demo"),
  createRepository("handbook-demo"),
]);

await mkdir(workerData, { recursive: true });
await mkdir(join(temporary, "server"), { recursive: true });
await chmod(join(temporary, "server"), 0o700);
await writeFile(
  join(temporary, "server", "worker-bootstrap-credential"),
  `${workerBootstrapCredential}\n`,
  { mode: 0o600 },
);
await mkdir(join(temporary, "pilot"), { recursive: true });
await mkdir(join(temporary, "pilot", "verdicts"), { recursive: true });
await writeFile(join(temporary, "pilot", "dashboard.json"), JSON.stringify({
  updated_at: "2026-08-09T12:00:00Z",
  projects: [
    {
      id: "factory-demo",
      name: "factory-demo",
      remote_identity: "github.com/example/factory",
      main_subject: "Show every project product on the overview",
      provider_status: "configured",
      environments: [
        {
          name: "Production",
          status: "available",
          release_label: "factory-e2e-release",
          health: "healthy",
        },
      ],
    },
    {
      id: "handbook-demo",
      name: "handbook-demo",
      remote_identity: "github.com/example/handbook",
      main_subject: "Document the product overview",
      provider_status: "not_configured",
      environments: [],
    },
  ],
}, null, 2));
const pilotStages = ["Triage", "Specification", "Implement + Test", "Review", "Verify"];
await writeFile(join(temporary, "pilot", "config.json"), JSON.stringify({
  _note: "browser fixture",
  enabled: true,
  poll_seconds: 10,
  timeout_seconds: 60,
  auto_merge: true,
  auto_answer: false,
  max_stage_attempts: 2,
  allow_any_worker: true,
  allowed_workers: [],
  max_parallel_subtasks: 2,
  day_cap_usd: 20,
  deploy_staging_cmd: "deploy",
  owner_chat_url: "https://example.test/chat",
  owner_ui_url: "https://example.test/ui",
  stages: pilotStages.map((workflow) => ({
    workflow,
    workers: { low: "Real local worker", medium: "Real local worker", high: "Real local worker" },
  })),
  skip_stages_for_low: ["Review"],
  stopped_pipelines: [pausedHTTPSWork, completedHTTPSWork],
  stage_base_usd: Object.fromEntries(pilotStages.map((stage) => [stage, 1])),
  complexity_factor: { low: 1, medium: 2, high: 3 },
  work_cap_usd: { low: 2, medium: 4, high: 8 },
  ntfy_topic: "factory", ntfy_server: "https://ntfy.sh", ntfy_owner_topic: "owner",
  project_providers: [
    { remote_identity: "github.com/example/factory", type: "factory" },
  ],
  brain_chain: [{ cli: "codex", model: "gpt", provider: "openai", note: "first" }],
}, null, 2));
await writeFile(join(temporary, "pilot", "work_status.json"), JSON.stringify({
  [pausedHTTPSWork]: {
    state: "stopped_owner",
    text: "Пауза для проверки возобновления через HTTPS-прокси.",
  },
}, null, 2));
await writeFile(join(workerData, "worker-id"), `${workerID}\n`, { mode: 0o600 });
await writeFile(
  workerConfig,
  `server = ${JSON.stringify(e2eServerOrigin)}
name = "Real local worker"
max_concurrent = 1
data_directory = ${JSON.stringify(workerData)}

[repositories.factory-demo]
path = ${JSON.stringify(factoryRepository)}

[repositories.handbook-demo]
path = ${JSON.stringify(handbookRepository)}
`,
);

const server = spawn(
  serverBinary,
  ["-listen", e2eServerAddress, "-database", database],
  {
    cwd: root,
    env: {
      ...process.env,
      HOME: temporary,
      FACTORY_DATA_HOME: temporary,
      PATH: `${fakeBin}${delimiter}${process.env.PATH ?? ""}`,
    },
    stdio: "inherit",
  },
);

const proxyKey = process.env.FACTORY_E2E_TLS_KEY;
const proxyCertificate = process.env.FACTORY_E2E_TLS_CERTIFICATE;
if (!proxyKey || !proxyCertificate) {
  throw new Error("FACTORY_E2E_TLS_KEY and FACTORY_E2E_TLS_CERTIFICATE are required");
}

// This is deliberately a real TLS hop, not a mocked Origin header. It strips
// client-supplied forwarding metadata before adding the one trusted loopback
// view that the control plane accepts.
const tlsProxy = createHTTPSServer({
  key: await readFile(proxyKey),
  cert: await readFile(proxyCertificate),
}, (clientRequest, clientResponse) => {
  const headers = { ...clientRequest.headers };
  for (const header of ["forwarded", "x-forwarded-for", "x-real-ip", "x-forwarded-host", "x-forwarded-proto"]) {
    delete headers[header];
  }
  headers.host = e2eServerAddress;
  headers["x-forwarded-host"] = clientRequest.headers.host ?? e2eProxyAddress;
  headers["x-forwarded-proto"] = "https";
  const upstream = proxyRequest({
    host: "127.0.0.1",
    port: e2eBackendPort,
    method: clientRequest.method,
    path: clientRequest.url,
    headers,
  }, (upstreamResponse) => {
    clientResponse.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
    upstreamResponse.pipe(clientResponse);
  });
  upstream.on("error", () => {
    if (!clientResponse.headersSent) clientResponse.writeHead(502);
    clientResponse.end("HTTPS proxy could not reach the control plane");
  });
  clientRequest.pipe(upstream);
});
await new Promise((resolveProxy, rejectProxy) => {
  tlsProxy.once("error", rejectProxy);
  tlsProxy.listen(e2ePort, "127.0.0.1", resolveProxy);
});

const worker = spawn(
  workerBinary,
  ["--config", workerConfig],
  {
    cwd: root,
    env: {
      ...process.env,
      HOME: temporary,
      FACTORY_DATA_HOME: temporary,
      PATH: `${fakeBin}${delimiter}${process.env.PATH ?? ""}`,
    },
    stdio: "inherit",
  },
);

async function serverJSON(path, init = {}) {
  const response = await fetch(`${e2eServerOrigin}${path}`, init);
  if (!response.ok) throw new Error(`fixture API ${path} returned ${response.status}: ${await response.text()}`);
  return response.json();
}

async function waitForFixtureWorker() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      const body = await serverJSON("/api/v1/workers");
      const worker = body.workers?.find((candidate) => candidate.id === workerID);
      if (worker?.online && worker.health === "healthy") return worker;
    } catch {
      // The Go listener and worker registration start independently.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error("HTTPS proxy fixture worker did not become healthy");
}

async function waitForFixtureTask(taskID) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const detail = await serverJSON(`/api/v1/tasks/${taskID}`);
    if (detail.task.state === "succeeded") return detail;
    if (detail.task.state === "failed" || detail.task.state === "cancelled") {
      throw new Error(`HTTPS proxy fixture task ${taskID} ended ${detail.task.state}`);
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error(`HTTPS proxy fixture task ${taskID} did not finish`);
}

async function createHTTPSProxyFixture() {
  const realWorker = await waitForFixtureWorker();
  const repository = realWorker.repositories.find((candidate) => candidate.key === "factory-demo");
  if (!repository) throw new Error("HTTPS proxy fixture could not find factory-demo repository");
  const revisions = new Map();
  for (const stage of pilotStages) {
    const workflow = await serverJSON("/api/v1/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_key: `https-proxy-${stage}`, title: stage,
        summary: `HTTPS proxy fixture for ${stage}`,
        instructions: `Complete ${stage} for the HTTPS proxy browser fixture.`,
      }),
    });
    revisions.set(stage, workflow.workflow.current_revision.id);
  }
  let sequence = 0;
  async function completeStage(base, stage) {
    sequence += 1;
    const created = await serverJSON("/api/v1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_key: `https-proxy-${sequence}`,
        title: `[auto] [${pilotStages.indexOf(stage) + 1}/${pilotStages.length} ${stage}] ${base}`,
        context: "A deterministic pipeline history for HTTPS reverse-proxy proof.",
        worker_id: workerID,
        repository_id: repository.id,
        timeout_seconds: 60,
        workflow_revision_id: revisions.get(stage),
      }),
    });
    const detail = await waitForFixtureTask(created.task.id);
    if (stage === "Review" || stage === "Verify") {
      await writeFile(join(temporary, "pilot", "verdicts", `${detail.task.id}.json`), JSON.stringify({ action: "advance" }));
    }
  }
  await completeStage(pausedHTTPSWork, "Triage");
  for (const stage of pilotStages) await completeStage(completedHTTPSWork, stage);
}

await createHTTPSProxyFixture();

let stopping = false;
async function stopChild(child, signal) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise((resolveStop) => {
    child.once("exit", resolveStop);
    if (!child.kill(signal)) resolveStop();
  });
}

async function stopProxy() {
  await new Promise((resolveStop) => tlsProxy.close(resolveStop));
}

async function stop(signal = "SIGTERM", exitCode = 0) {
  if (stopping) return;
  stopping = true;
  await stopChild(worker, signal);
  await stopProxy();
  await stopChild(server, signal);
  await rm(temporary, { recursive: true, force: true });
  await rm(legacyRoot, { recursive: true, force: true });
  process.exit(exitCode);
}

process.on("SIGINT", () => void stop("SIGINT"));
process.on("SIGTERM", () => void stop("SIGTERM"));
server.once("exit", (code) => {
  if (!stopping) void stop("SIGTERM", code ?? 1);
});
worker.once("exit", (code) => {
  if (!stopping) void stop("SIGTERM", code ?? 1);
});
