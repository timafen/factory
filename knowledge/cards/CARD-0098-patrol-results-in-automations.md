# CARD-0098: находки патрулей в Automations

Implementation commit: b5dd4d62827995f2f65c6f544d569b4b28df99f0 — Tasks API сообщает устойчивый признак patrol, а Work фильтрует кешированную историю

## HEAD

- Status: Implemented, awaiting Review
- Branch: `factory/00762e4a-125-d3e36cea-038`
- Implementation commit: `b5dd4d62827995f2f65c6f544d569b4b28df99f0`
- What changed: Tasks API вычисляет `is_patrol` из durable schedule Automation; Work отбрасывает его из свежей и кешированной истории. DOM-типы e2e восстановили сборку.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` → PASS; `npm run build` → PASS; целевой Playwright schedule Automation → 1/1 PASS.
- Next action: провести Review поставки.

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

### 2026-08-12 — Implement

Подключены DOM-типы для Playwright e2e и зафиксирован актуальный web bundle. Typecheck и build пршли; целевой schedule Automation прошёл 1/1. Полный Playwright остановился на несвязанном устаревшем expectation заголовка Work.
