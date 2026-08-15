Implementation commit: d27576bf659c9d2c7e01388bdae9efe56a26eaa1 — ранее проверенный вариант очищает реальный blocking fake `gh`, его process group и временный корень после TERM, INT и HUP.

# CARD-0097 — Прерванные worker-тесты очищают fake `gh` и `/tmp`

## HEAD

- Status: SPECIFIED — готово к Implement на свежем `main`.
- Branch: `factory/7d3ce3b5-7cb-e11be434-04b`.
- Specification: `knowledge/specs/worker-test-interruption-cleanup.md`.
- Owner impact: остановка worker-теста не оставляет блокирующие fake `gh`, их
  process group и тестовые каталоги в `/tmp`.
- Scope: test-only cleanup после `TERM`, `INT`, `HUP`, контролируемая регрессия
  с настоящим managed-clone `block-all` и сохранение существующих проверок.
- Out of scope: старый мусор, production `gh`/clone, release-тесты и гарантия
  после `SIGKILL` без внешнего supervisor.
- Prior implementation: `d27576bf659c9d2c7e01388bdae9efe56a26eaa1`
  зафиксировал рабочий вариант в опубликованной ветке предыдущего конвейера;
  Implement должен сверить его с текущим `main` и записать свой кодовый commit.
- One next action: реализовать три test-only файла по спецификации и выполнить
  целевую регрессию `TestWorkerTestInterruptionCleanup`.

## LOG

### 2026-08-14 — Specification

На свежем `main` повторно подтверждена причина: managed-clone fake `gh` ждёт
`release`, acquisition запущен с `context.Background()`, а `runCommand` создаёт
отдельную process group. Определён test-only lifecycle, который ставит обработчик
до `main.Run`, регистрирует настоящий blocking fake `gh`, на TERM/INT/HUP
останавливает и reap-ит группу, затем удаляет собственный temp-root. Проверка
дожидается readiness без sleeps и после выхода подтверждает исчезновение PID,
PGID и каталога; `SIGKILL` явно исключён из контракта.

### 2026-08-12 — Предыдущая реализация

В предыдущем опубликованном конвейере реальный сценарий `block-all` был связан с
обработчиком `TestMain`; целевой и полный Go-наборы прошли. Ссылка сохранена как
технический ориентир, но текущая Specification-поставка содержит только знания.
