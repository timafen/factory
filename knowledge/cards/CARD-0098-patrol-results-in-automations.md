# CARD-0098: находки патрулей в Automations

Implementation commit: 232c46a11d83b75512b70f9a69d3f923602b1267 — Tasks API сообщает устойчивый признак patrol, а Work фильтрует кешированную историю

## HEAD

- Status: Implemented, awaiting Review
- Branch: `factory/50900d82-810-6fad25a8-6e0`
- Implementation commit: `232c46a11d83b75512b70f9a69d3f923602b1267`
- What changed: Tasks API вычисляет `is_patrol` из durable schedule Automation; Work отбрасывает этот признак при объединении свежей и кешированной истории.
- Evidence: `go test ./internal/controlplane/...` → PASS; `npm test -- --run src/Work.test.ts` → 16/16 PASS; `git diff --check` → PASS.
- Next action: повторить Review на свежей ветке.

## LOG

### 2026-08-12 — Implement

Добавлен явный `is_patrol` в Tasks API и production-shaped регрессия для schedule Automation с patrol title; Work фильтрует такой task до построения разделов и при merge кеша, включая `origin: orchestrator`. Целевой Go-набор и Work-тесты зелёные; typecheck заблокирован существующей ошибкой `Navigator.serviceWorker` в e2e.

### 2026-08-12 — Implement

Реализована durable-фильтрация Factory Pipeline Patrol до `LIMIT + 1`, защитная фильтрация Work и явная подпись finding в Automation Runs. Добавлены регрессии для cursor, обычных типов задач, run без задачи, deleted task и task link. Полный Vitest прошёл 164/164; полный Go-набор выявил только исправленную нестабильность новой фикстуры, после чего целевая backend-регрессия прошла.

### 2026-08-12 — Specification

## Контекст

Патрульные задачи сейчас попадают в общий API задач и поэтому отображаются в Work как обычная работа. Детали Automation уже содержат occurrence, состояние, diagnostic и связанную задачу, но это поведение нужно закрепить спецификацией и регрессиями.

## Объём

Исключить только `workClassPatrol` из всех списков Work с корректной пагинацией; сохранить остальные типы задач. В Runs Automation detail явно показывать finding/diagnostic, конечное состояние и связанную задачу, если она существует, включая reload и pagination.

## Проверка

Целевая проверка: `cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx`.
