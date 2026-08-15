# CARD-0177 — Честная цена дублей, отмен и незавершённых конвейеров

Implementation commit: 9bebae3aa98581166fc33e82c310da430938bc15 — служебные scheduled-запуски Factory patrol исключены из цены незавершённых конвейеров.

## HEAD

- Status: READY FOR REVIEW; полный Verify пройден.
- Branch: `factory/1dd85fbc-c50-e3517592-c5f`.
- Implementation commit: `9bebae3aa98581166fc33e82c310da430938bc15`.
- What changed: dashboard считает usage по событиям в 24-часовом окне и
  раскладывает цену по отменам, ранним повторам стадий и хвостам без merge.
  Scheduled-запуски Factory patrol отсекаются до загрузки usage; Overview
  показывает нижнюю границу, окно, покрытие и legacy fallback.
- Evidence: полный Go/Python Verify → PASS, 357 Python tests OK;
  UI lint/typecheck/test/build → PASS, 183 tests; browser-critical → 5 passed.
- Next action: провести независимое ревью текущего implementation-коммита.

## LOG

### 2026-08-15 — Specification

По фактическому коду установлено: `write_dashboard` ограничивается 60 задачами,
привязывает весь расход к `created_at` и считает waste только для
failed/cancelled. Зафиксированы timestamp-окно usage, три непересекающиеся
категории, dead-end grace, покрытие неизвестной цены, legacy fallback и целевые
регрессионные проверки. Номер CARD-0177 проверен по свежему `origin/main` и всем
опубликованным веткам.

### 2026-08-15 — Implement

Добавлен событийный 24-часовой расчёт известной цены и непересекающаяся
классификация cancellation → duplicate → unfinished. Интерфейс показывает три
причины, временное окно, покрытие и предупреждает о нижней границе. Целевые
Python-тесты: 3 OK; Overview: 31 passed; web build и `git diff --check`: success.

### 2026-08-15 — Implement

После восстановления реализации в ветке проверки установлен зафиксированный
набор web-зависимостей и выполнена обязательная проверка типов:
`npx tsc -p tsconfig.app.json --noEmit` завершилась успешно. Этап возвращён на
ревью только после добавления этого результата в доказательства.

### 2026-08-15 — Implement

Исправлён дефект Verify: распознаватель служебного Factory patrol переиспользован
в расчёте waste, поэтому `Factory patrol: scheduled …` с реальным usage даёт
нулевые суммы и не увеличивает покрытие. Регрессионный набор метрик: 4 tests OK.
Полный Verify после rebase: build/format/vet/boundary и все Go-пакеты PASS;
357 Python-тестов, 183 UI-теста и 5 browser-critical сценариев прошли; lint,
typecheck и production build успешны.
