# CARD-0097 — Патруль маршрутизируется на дешёвую модель

Implementation commit: 2687f006d0ac8c6e6376c75afce4a1c4616a1283 — текущий кодовый слепок для Specification; продуктовая реализация запланирована следующим этапом.

## HEAD

- Status: Specification — awaiting Implement + Test.
- Branch: `factory/4d76c830-ed6-d9e0b4a3-596`.
- Specification: `knowledge/specs/pipeline-patrol-cheap-model.md`.
- Owner contract: hourly patrol uses `gpt-5.6-terra`; accept only with at
  least 90% useful-finding retention and no more than 5 percentage points of
  false-positive increase against `gpt-5.6-sol` over 24 hours.
- Evidence basis: fresh remote `main` read and current Automation, scheduler,
  protocol, worker supervisor and Pilot implementation inspected.

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
