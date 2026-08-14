# CARD-0127 — Закрыть дубликат SA4000 в lifecycle-тесте

Implementation commit: c6d8644aaf9700f10365891a30a0679fff45c73b — устранено самосравнение в `internal/worker/attempt_lifecycle_test.go` и добавлены исходные документы CARD-0126.

## HEAD

- Status: Closed — duplicate of CARD-0126.
- What changed: новых изменений кода нет; исходное исправление уже вошло в
  `main` через PR №214.
- Evidence: `just staticcheck` подтверждает, что прежний `SA4000` не
  воспроизводится.
- Scope: только закрытие дубликата. Остальной долг `CARD-0040` и отдельная
  блокировка browser suite исключены.

## Решение

Эта карточка фиксирует решение владельца закрыть задачу без дальнейшей
реализации. Каноническая карточка исправления —
`knowledge/cards/CARD-0126-staticcheck-attempt-lifecycle.md`; она описывает
проверку lifecycle и исходную поставку. `CARD-0040` не является карточкой этой
работы и не меняется.

ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle_test.go
ГОТОВО-КОГДА: команда just staticcheck
