# CARD-0097 — Патруль маршрутизируется на дешёвую модель

Implementation commit: 8f46c560336cdbceca28215b09e4dd34331aa31f — дорогая модель назначена эталоном теневого 24-часового pair-run.

## HEAD

- Status: Implemented — live 24-hour shadow window remains pending.
- Branch: `factory/9bab6779-999-91d2b471-522`.
- Implementation commit: `8f46c560336cdbceca28215b09e4dd34331aa31f`.
- What changed: evaluator uses `gpt-5.6-sol` findings as the approved reference,
  labels the same-input terra result and records the verdict source in audit.
- Safety: until the full window and both thresholds pass, effective model is
  `gpt-5.6-sol`; malformed/missing audit data never enables terra.
- Evidence: `python3 -m unittest pilot.test_pilot.PatrolModelEvaluationTests` → 6 pass.
- Next action: run the approved live same-input shadow window for 24 hours and attach its retention and false-positive delta.

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

### 2026-08-12 — Implement

Added the 24-hour pair-run evaluator with a deterministic input hash, stable
finding keys, explicit `useful`/`false_positive` verdicts, retention and
false-positive-delta gates. Its separate JSON audit is immutable after the
decision; incomplete, mismatched, or unreviewed data keeps the effective model
on sol. `python3 -m unittest pilot.test_pilot.PatrolModelEvaluationTests` passed
(5 tests). A live 24-hour run has not yet completed, so no production switch or
acceptance metrics are recorded.

### 2026-08-12 — Implement

The owner approved `gpt-5.6-sol` as the reference for a same-input shadow run.
The evaluator now labels matching terra findings as useful and terra-only
findings as false positives, while recording sol as the verdict source and
leaving the effective model unchanged. The six evaluator tests pass. No live
24-hour metrics are claimed: the deployed main service cannot dispatch a model
override yet, and repository work must not mutate Factory state.
