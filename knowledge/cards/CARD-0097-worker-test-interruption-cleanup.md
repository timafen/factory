# CARD-0097 — Прерванные worker-тесты очищают fake `gh` и `/tmp`

Implementation commit: 2eae3cc07562ba731b35a22335fc127e53971029 — штатный lifecycle worker-тестов очищает blocking fake gh, его process group и временный корень после TERM, INT и HUP.

## HEAD

- Status: IMPLEMENTED, проверки пройдены.
- Branch: factory/8e8a1ce4-e06-afa4b014-acf
- Implementation commit: 2eae3cc07562ba731b35a22335fc127e53971029
- What changed: обработчик включён для каждого `TestMain` worker-пакета, а не
  только helper-режима; все managed-clone sync-каталоги регистрируются штатно.
- Evidence: `go test -timeout 5m ./...` и `npx tsc -p tsconfig.app.json --noEmit` → PASS (2026-08-15).
- One next action: перед слиянием провести review изменения.
- Specification: `knowledge/specs/worker-test-interruption-cleanup.md`.
- Owner impact: остановка worker-теста не оставляет блокирующие fake `gh`, их
  process group и тестовые каталоги в `/tmp`.
- Scope: cleanup test-helper после `TERM`, `INT`, `HUP`, новая контролируемая
  регрессия и сохранение существующих managed-repository/process-group тестов.
- Out of scope: уже накопленный мусор, production `gh`/clone, release-тесты и
  гарантия после `SIGKILL` без внешнего supervisor.

## LOG

### 2026-08-15 — Implement

В `web/` установлены зависимости строго по lock-файлу; обязательная проверка
`npx tsc -p tsconfig.app.json --noEmit` прошла. Рабочая ветка перенесена на
актуальный `main`; кодовая реализация остаётся в указанном implementation commit.

### 2026-08-15 — Implement

Повторная проверка после переноса на выделенную ветку подтвердила штатную
очистку fake `gh`, process group и `/tmp`-корня после TERM, INT и HUP.
Целевой worker-набор и полный `go test -timeout 5m ./...` завершились успешно.

### 2026-08-15 — Implement

Уборка TERM/INT/HUP перенесена в обычный lifecycle `TestMain` worker-тестов.
Регрессия запускает настоящий вложенный `go test`, прерывает его process group
и подтверждает отсутствие blocking fake `gh` group и выделенного `/tmp`-корня.

### 2026-08-15 — Implement

После перебазирования на свежий `main` целевой сценарий подтвердил очистку
blocking fake `gh`, его PID/process group и выделенного `/tmp`-корня после
TERM, INT и HUP. Целевой worker-набор и единственный полный `go test -timeout
5m ./...` прошли.

### 2026-08-12 — Implement

Регрессия переведена с синтетического helper на существующий managed-clone
сценарий `block-all`. Обработчик регистрируется до readiness, cleanup завершает
группу с TERM→KILL fallback, а реальные `Cmd.Wait` и родительский `Wait`
выполняются при успешном и аварийном исходе. Целевой и полный Go-наборы прошли.

### 2026-08-12 — Implement

Добавлен test-only helper, который после TERM/INT/HUP завершает созданную process group,
дожидается её завершения с ограничением и удаляет выделенный temp-root. Table-driven
регрессия подтвердила исчезновение PID, PGID и каталога; целевые и полный Go-наборы зелёные.

### 2026-08-12 — Specification

Причина утечки подтверждена в `repository_coordination_test.go`: fake `gh`
блокируется на release-файле, запуск acquisition использует
`context.Background()`, а `runCommand` создаёт отдельную process group.
Выбран test-only lifecycle helper с независимым temporary root и реестром
созданных групп. Контролируемый дочерний run будет получать `TERM`, `INT` и
`HUP`; тест подтвердит исчезновение PID/PGID и каталога. `SIGKILL` исключён из
контракта, поскольку killed-процесс не выполняет defer/cleanup.
