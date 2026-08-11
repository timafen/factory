# CARD-0075 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: Specification — awaiting implementation.
- Branch: `factory/40e232e4-8c0-02e2b14c-62e`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: отсутствует — эта ветка содержит только
  спецификацию; этап Implement обязан записать сюда полный SHA своего
  предшествующего коммита с кодом до финального коммита карточки.
- What changes: отложенный restart Пилота будет поставлен после release-info
  и выполнится только при свободном общем release-lock, поэтому прошлый выпуск
  не оборвёт следующий.
- Next action: Implement меняет только release-драйвер и его shell-регрессию.

## LOG

### 2026-08-11 — Specification

Проверен фактический порядок в `ops/fx-factory-release`: transient restart
создаётся до записи `$INFO` и не привязан к `$LOCK`. Выбран lock как единая
граница поколений выпуска; сравнение только с release-info оставляет TOCTOU
окно. Реализация и запуск тестов намеренно оставлены следующему этапу.
