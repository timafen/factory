# CARD-0097 — Прерванные worker-тесты очищают fake `gh` и `/tmp`

Implementation commit: отсутствует — эта Specification-стадия намеренно не создаёт код; Implement добавит существующий полный SHA до обновления карточки.

## HEAD

- Status: READY FOR IMPLEMENT.
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

### 2026-08-12 — Specification

Причина утечки подтверждена в `repository_coordination_test.go`: fake `gh`
блокируется на release-файле, запуск acquisition использует
`context.Background()`, а `runCommand` создаёт отдельную process group.
Выбран test-only lifecycle helper с независимым temporary root и реестром
созданных групп. Контролируемый дочерний run будет получать `TERM`, `INT` и
`HUP`; тест подтвердит исчезновение PID/PGID и каталога. `SIGKILL` исключён из
контракта, поскольку killed-процесс не выполняет defer/cleanup.
