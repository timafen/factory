# CARD-0097 — Патруль маршрутизируется на дешёвую модель

Implementation commit: 9fa8ca06d722bccb8cff9a6293354b80f071732f — patrol сохраняет и передаёт точный override `gpt-5.6-terra` в Codex.

## HEAD

- Status: Implemented — awaiting production 24-hour pair-run gate.
- Branch: `factory/aa5fd162-32d-fa5313dc-d02`.
- Implementation commit: `9fa8ca06d722bccb8cff9a6293354b80f071732f`.
- What changed: the provisioned hourly patrol snapshots `gpt-5.6-terra` into
  its occurrence and task; the worker sends it as `codex exec -m`.
- Safety: unknown overrides are rejected before execution; other tasks retain
  no override.
- Evidence: `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol|Model)'`,
  `go test ./internal/worker -run 'Test.*(Model|Prompt|Codex)'`, and `go test ./...` pass.
- Next action: implement and run the 24-hour paired evaluator before enabling a production switch.

## LOG

### 2026-08-12 — Specification

The previous Triage branch named in the task was not published on `origin`, so
no reset was possible. Fresh `origin/main` shows the patrol instruction in
`internal/controlplane/pipeline_patrol.go`, durable scheduling in
`schedule_runtime.go`, worker-wide runtime selection, and a Pilot brain chain
where `gpt-5.6-terra` is only a fallback. The specification therefore requires
an explicit model override through the Task/Claim/supervisor path plus a
same-input 24-hour terra/sol pair-run and fail-closed acceptance decision.

Card number/path check: `CARD-0097-pipeline-patrol-cheap-model.md` is absent
from fresh `origin/main`; the published refs were queried for the supplied
previous branch and no matching branch was available.

### 2026-08-12 — Implement

The durable automation, occurrence and task snapshots now carry an allow-listed
Codex model ID. Provisioning writes `gpt-5.6-terra` for the pipeline patrol;
dispatch and the worker supervisor preserve it through to the Codex command.
Schedule/patrol and worker target tests passed, followed by `go test ./...`.
The specification's 24-hour evaluator and production acceptance decision remain
the next stage; no model switch is claimed from simulated tests.
