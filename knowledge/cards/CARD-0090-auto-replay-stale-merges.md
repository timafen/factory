Implementation commit: 1deb91c63adb734322361b3981e91eb85bd9962b — долговечный broker не публикует успех до сохранения terminal-состояния; это базовая гарантия для последующего восстановления выпуска.

# CARD-0090 — Автоматически восстановить отставший выпуск Factory

## HEAD

- Status: Specification ready.
- Specification: `knowledge/specs/auto-replay-stale-factory-merges.md`.
- Scope: только восстановление потерянного автоматического намерения Factory;
  ручной выпуск, сторонние сигнальные ошибки и торговый staging исключены.
- Outcome: Pilot сопоставит актуальный `origin/main` с надёжно прочитанным
  установленным SHA, единожды зарезервирует объединённый выпуск и безопасно
  продолжит его после release-lock.

## Наблюдения

- CARD-0051 уже сохраняет retry после внешней блокировки, а CARD-0084 —
  durable generation/broker status; оба механизма требуют отдельного backfill
  при пустой очереди.
- Установленный SHA уже атомарно публикуется release driver в `release-info`;
  для Pilot нужен строгий read-only контракт вместо разбора текста.
- Divergent SHA трактуется как возможный rollback и не должен автоматически
  переигрываться main.

## Следующее действие

Реализовать и проверить reconciliation только для Factory по указанной
спецификации.
