# CARD-0098: находки патрулей в Automations

Implementation commit: 7382a3fd8c4b47a2a6c915354200fe249088fbe9 — находки патрулей исключены из Work и явно показаны в Runs Automation

## HEAD

- Status: Implemented
- Branch: `factory/e3390a8c-8ac-f467446e-3ae`
- Implementation commit: `7382a3fd8c4b47a2a6c915354200fe249088fbe9`
- What changed: patrol-задачи исключаются из API и всех разделов Work без разрыва cursor-пагинации; Runs подписывает finding и сохраняет task link/tombstone.
- Evidence: `go test ./internal/controlplane/...` → PASS; целевые Vitest 78/78 → PASS; lint, typecheck, build → PASS.
- Next action: проверить экран `/automations` после выпуска.

## LOG

### 2026-08-12 — Implement

Реализована durable-фильтрация Factory Pipeline Patrol до `LIMIT + 1`, защитная фильтрация Work и явная подпись finding в Automation Runs. Добавлены регрессии для cursor, обычных типов задач, run без задачи, deleted task и task link. Полный Vitest прошёл 164/164; полный Go-набор выявил только исправленную нестабильность новой фикстуры, после чего целевая backend-регрессия прошла.

### 2026-08-12 — Specification

## Контекст

Патрульные задачи сейчас попадают в общий API задач и поэтому отображаются в Work как обычная работа. Детали Automation уже содержат occurrence, состояние, diagnostic и связанную задачу, но это поведение нужно закрепить спецификацией и регрессиями.

## Объём

Исключить только `workClassPatrol` из всех списков Work с корректной пагинацией; сохранить остальные типы задач. В Runs Automation detail явно показывать finding/diagnostic, конечное состояние и связанную задачу, если она существует, включая reload и pagination.

## Проверка

Целевая проверка: `cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx`.
