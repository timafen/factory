# CARD-0074 — Спецификация публикует документы до передачи в разработку

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/c0f1ac84-c62-bc22090b-fef`.
Implementation commit: 6e6378b8dae717abb7702fd9f03fad7a5d51b2d3 — новая revision Specification публикует документы перед передачей.
- What changed: migration 023 устанавливает точный prompt для включённой
  Specification и сохраняет прежнюю revision в истории. Handoff-тест теперь
  передаёт BRANCH, полный HEAD и PUSHED: yes опубликованной ветки.
- Evidence: `go test ./internal/controlplane -run 'Test.*Specification.*Migration'` → PASS; `python3 -m unittest -v pilot.test_pilot.SpecificationBranchHandoffTests` → 8 tests, OK.
- Next action: Verify проверяет миграцию и полные регрессии workflow.

## LOG

### 2026-08-11 — Implement

Добавлена immutable migration 023: она создаёт детерминированную revision для
включённой Specification, требует документ, карточку CARD-0074, commit/push и
строки BRANCH/HEAD/PUSHED. Upgrade-тест подтверждает exact prompt, историю,
request key и неизменность disabled workflow; handoff-тест сохраняет строгую
проверку опубликованной непустой ветки. Целевые Go и Python проверки прошли.
