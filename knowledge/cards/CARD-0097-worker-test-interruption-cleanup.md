# CARD-0097 — Прерванные worker-тесты очищают fake `gh` и `/tmp`

Implementation commit: b6bea3484d3589068671e4b9e6290f7cb5365526 — test-helper очищает fake gh, process group и временный корень после TERM, INT и HUP.

## HEAD

- Status: IMPLEMENTED.
- Branch: factory/49c3275e-3e7-966d9473-3aa
- Implementation commit: b6bea3484d3589068671e4b9e6290f7cb5365526
- What changed: добавлен Unix-only controlled helper с ограниченным TERM→KILL fallback и регрессия для трёх сигналов; production-файлы не затронуты.
- Evidence: `go test ./internal/worker -run '^TestWorkerTestInterruptionCleanup$' -count=1` → PASS; `go test -timeout 5m ./...` → PASS.
- One next action: проверить поведение на целевой CI/Unix-стенде при интеграции.
- Specification: `knowledge/specs/worker-test-interruption-cleanup.md`.
- Owner impact: остановка worker-теста не оставляет блокирующие fake `gh`, их
  process group и тестовые каталоги в `/tmp`.
- Scope: cleanup test-helper после `TERM`, `INT`, `HUP`, новая контролируемая
  регрессия и сохранение существующих managed-repository/process-group тестов.
- Out of scope: уже накопленный мусор, production `gh`/clone, release-тесты и
  гарантия после `SIGKILL` без внешнего supervisor.
- One next action: Implement создаёт кодовый коммит, записывает его полный SHA
  в первую строку этой карточки и выполняет test-plan спецификации.

## LOG

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
