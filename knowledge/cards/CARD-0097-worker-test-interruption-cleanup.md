# CARD-0097 — Прерванные worker-тесты очищают fake `gh` и `/tmp`

Implementation commit: 5863c3f639cc3a5c2be2bcdb2e7d9267e633bff5 — реальный blocking fake gh очищается вместе с process group и временным корнем после TERM, INT и HUP.

## HEAD

- Status: IMPLEMENTED, готово к повторной проверке.
- Branch: factory/60e483c9-a17-bf5ad3aa-6b3
- Implementation commit: 5863c3f639cc3a5c2be2bcdb2e7d9267e633bff5
- What changed: обработчик ставится до `main.Run`; реальный `block-all` fake `gh`
  регистрирует process group, которая очищается с ожиданием production `Wait`.
- Evidence: целевой worker-набор → PASS; `go test -timeout 5m ./...` → PASS (2026-08-15).
- One next action: повторно проверить реализацию перед слиянием.
- Specification: `knowledge/specs/worker-test-interruption-cleanup.md`.
- Owner impact: остановка worker-теста не оставляет блокирующие fake `gh`, их
  process group и тестовые каталоги в `/tmp`.
- Scope: cleanup test-helper после `TERM`, `INT`, `HUP`, новая контролируемая
  регрессия и сохранение существующих managed-repository/process-group тестов.
- Out of scope: уже накопленный мусор, production `gh`/clone, release-тесты и
  гарантия после `SIGKILL` без внешнего supervisor.

## LOG

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
