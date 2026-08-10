# CARD-0055 — Сокращение ожидания между этапами конвейера

## HEAD

Implementation commit: f50077059fedfbb62ae4d8b87a5af31f59b89875 — Patrol продолжает конвейер через 120 секунд, а обзор оценивает долю ожидания между этапами относительно соседних 7-дневных окон.

- Status: Implemented and tested; ready for Review.
- Branch: `factory/be308045-733-a46e018c-942`.
- What changed: ожидание Patrol сокращено с 600 до 120 секунд; старая инструкция заменяется на месте с сохранением остального контекста. В обзоре показана цель `stage_handoff_wait ≤10%` за текущие 7 дней рядом с непосредственно предыдущими 7 днями.
- Evidence: целевые Go-тесты — PASS; 14 тестов `Overview` — PASS; web build и lint — PASS; `git diff --check` — PASS.
- One next action: провести Review реализации и подтвердить смысл метрики на реальных 7-дневных данных.

## LOG

### 2026-08-10 — Implement

Patrol теперь ждёт 120 секунд вместо 600. Повторное provision безопасно обновляет точную старую инструкцию, не дублирует новую и не теряет соседний пользовательский контекст. API рассчитывает цель ожидания между этапами с порогом 10%, текущей долей и долей непосредственно предыдущего окна; Overview показывает это сравнение для 7 дней. Проверки: `go test ./internal/controlplane -run 'Test(PipelinePatrol|EfficiencyTarget)' -count=1` — PASS; `npm test -- --run src/Overview.test.ts` — 14 PASS; `npm run build`, `npm run lint`, `git diff --check` — PASS.
