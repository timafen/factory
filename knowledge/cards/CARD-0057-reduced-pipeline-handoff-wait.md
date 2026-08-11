# CARD-0057 — Сокращённое ожидание между этапами

## HEAD

- Implementation commit: c4f73fbc1a7629a47bf7751327566e3a305d1b89 — патруль ждёт потерянный переход 450 секунд, а недельная цель получает вердикт только при выборке от пяти работ.
- Status: BLOCKED: production UI does not render in the browser end-to-end suite; the first scenario cannot find the «Обзор» heading and the remaining 17 do not run.
- Branch: `factory/489242af-865-0b171b7f-7f3`.
- What changed: безопасная пауза между этапами сокращена на 25%, до 450 секунд; в «Обзоре» появилась недельная цель ожидания ≤10% без преждевременного успеха на малой выборке.
- Evidence: чистый `go test ./...`, 159 Python-проверок, UI lint/typecheck/unit tests и production build — PASS; Playwright browser suite — FAIL до проверки результата.
- One next action: исправить рендер production UI в Playwright и повторить browser suite.

## LOG

### 2026-08-10 — Implement

Патруль обновляет прежнюю инструкцию ожидания с 600 до 450 секунд и сохраняет пользовательский контекст. API оставляет `met: null` при 0, 1 и 4 завершённых работах и формирует вердикт с порога 5; интерфейс использует тот же минимум. Целевые серверные, Python- и UI-тесты, проверка типов, линтер и production build прошли.

### 2026-08-10 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Ожидание патруля 450 секунд и миграция старой инструкции | `go test ./...` (чистый test cache) | PASS; включены `TestPipelinePatrolProvisionUsesExistingScheduleAndPreservesRuns` и `TestPipelinePatrolProvisionReplacesLegacyWait`. |
| Цель ожидания ≤10% только от пяти завершённых работ | `go test ./...`; `cd web && npm test` | PASS; серверная проверка сравнивает текущую и предыдущую доли, UI-проверки покрывают выборки 0, 1, 4 и 5. |
| Согласованное ускорение пилота | `python3 -m unittest pilot.test_pilot` | PASS, 159 tests; проверяется `STALL_WAIT == 450`. |
| Сборка и соседнее поведение интерфейса | `cd web && npm run lint && npm run typecheck && npm test && npm run build` | PASS; lint, typecheck, unit tests и production build. |
| Реальное отображение production UI | `cd web && npm run test:browser` | FAIL: после повторной сборки первый сценарий не находит «Обзор» за 8 с, скриншот пустой; 17 сценариев не запущены. |
