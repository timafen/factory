# CARD-0177 — Честная цена дублей, отмен и незавершённых конвейеров

Implementation commit: 8aa31c0fcd96b6499712cbd4bef4f5f7d2ca23f8 — добавлены непересекающиеся метрики цены отмен, дублей и незавершённых конвейеров с честным покрытием.

## HEAD

- Status: READY FOR REVIEW.
- Branch: `factory/d3316bcc-9e7-8b51962d-6b8`.
- Implementation commit: `8aa31c0fcd96b6499712cbd4bef4f5f7d2ca23f8`.
- What changed: dashboard считает usage по событиям в 24-часовом окне и
  раскладывает цену по отменам, ранним повторам стадий и хвостам без merge.
  Overview показывает нижнюю границу, окно, покрытие и legacy fallback.
- Evidence: `python3 -m unittest pilot.test_pilot.DashboardWasteMetricsTests` →
  3 tests OK; `npm test -- --run src/Overview.test.ts` → 31 passed;
  `npm run build` → success; `npx tsc -p tsconfig.app.json --noEmit` → success.
- Next action: провести ревью реализации метрик.

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
