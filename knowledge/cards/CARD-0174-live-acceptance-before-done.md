# CARD-0174 — Завершение только после живой приёмки

Implementation commit: de8e5d60934ee820a0bbfd59af0e2364d30c58f6 — исходная машина доставки восстанавливает точный Verify-снимок; реализация живой приёмки ещё не начата.

## HEAD

- Status: Specified — ожидает Implement.
- Specification: `knowledge/specs/live-acceptance-before-done.md`.
- Scope: durable post-release live acceptance без UI и SQLite migration.
- Owner result: «Задача выполнена» публикуется только после live PASS; live
  FAIL с причиной возвращает Verify в `Implement + Test`.
- Safe production fixture: read-only offline retained-worktree JSON проходит
  тот же parser, что фактический `/api/v1/workers`, не создавая и не очищая
  живые worktree.
- Next action: реализовать перечисленные в спецификации файлы и сначала
  запустить целевой Python-набор.

## LOG

### 2026-08-15 — Specification

Фактический `pilot/pilot.py` завершает generation непосредственно по broker
`succeeded`. Определена отдельная durable фаза `released`, acceptance operation
с тем же immutable generation ID, идемпотентные PASS/FAIL side effects и
fail-closed recovery. PASS единственный создаёт receipt, final success и Done;
FAIL сохраняет безопасную причину и возвращает работу в `Implement + Test`.

Production fixture выбран read-only: встроенный offline-retained snapshot и
живой workers snapshot проходят один parser. Проверка не вызывает janitor,
mutating API, systemd или worktree cleanup, но сохранённая живая запись
обязательно приводит к FAIL.

## Связи

- CARD-0084 — базовая durable машина слияния и выпуска.
- CARD-0048 — точечное подтверждение очистки offline retained-worktree.
- CARD-0092 — durable terminal status release broker.
