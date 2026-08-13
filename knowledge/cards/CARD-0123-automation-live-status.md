# CARD-0123 — Живой статус всех автоматик Фабрики

Implementation commit: b3bd0f556455f7e2559aede725787c0fdf703547 — экран Automation показывает единый снимок пользовательских и внутренних автоматик с понятным состоянием.

## HEAD

- Статус: Implemented — ожидает Review.
- Ветка: `factory/688cc94b-302-69ba2e6e-507`.
- Implementation commit: `b3bd0f556455f7e2559aede725787c0fdf703547` — отдельный
  `/api/v1/automation-status` объединяет пользовательские Automation, pilot,
  brain, release broker, deploy и janitor; UI опрашивает снимок каждые 5 секунд.
- Evidence: `go test ./internal/controlplane -run 'TestAutomationStatusIncludesFactoryServicesAndUnavailableData|Test.*Automation'` — PASS;
  `npm --prefix web run test -- --run App.test.tsx`, `typecheck` и `build` — PASS.
- Следующее действие: Review проверить полноту источников и правила устаревания.

## LOG

### 2026-08-13 — Specification

Подготовлена спецификация `knowledge/specs/automation-live-status.md`. На свежем
`origin/main` `/api/v1/automations` и `AutomationsView` покрывали только
пользовательские записи; внутренние pilot/brain/release/deploy/janitor в единой
выдаче отсутствовали, а статусы и общая индикация просрочки не соответствовали
контракту.

### 2026-08-13 — Implement

Добавлен read-only снимок `GET /api/v1/automation-status`: он содержит
пользовательские Automation и все пять внутренних категорий, не маскирует
нехватку журналов и передаёт русские состояния, объяснение результата и stale.
Экран `/automations` показывает снимок и опрашивает его без reload. Целевой Go
тест, App-тест, typecheck и production build прошли.
