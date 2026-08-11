Implementation commit: 3d1c61ac782572ff25d41772730287f321638294 — сохранение и показ причины каждого возврата Review

# CARD-0057 — Причины повторных возвратов Review

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/c19e8a62-a26-8fd0e1be-19f`.
- What changed: Pilot сохраняет короткую причину решения; массовый API отдаёт её только для возвратов Review и восстанавливает объяснение старых записей.
- What changed: раскрытая история работы показывает причину у каждого возврата, не скрывая одинаковые причины следующих кругов.
- Evidence: целевые Python и Go тесты — PASS; полный Vitest — 134/134 PASS; web lint, typecheck и production build — PASS. Полный Go-набор прошёл все затронутые пакеты и остановился на прежней гонке в неизменённом `internal/worker`.
- One next action: Human merge — проверить понятность повторных причин на `/work`.

## LOG

### 2026-08-10 — Implement

Причина возврата теперь проходит от решения Pilot через ограниченный массовый API до истории на экране. Тест интерфейса воспроизводит два последовательных возврата Review с одинаковой причиной и подтверждает две отдельные подписи; API-тест также покрывает старую запись без короткой причины. После реализации ветка перебазирована на свежий `origin/main`.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Каждое решение Review сохраняет короткую причину | `python3 -m unittest -v pilot.test_pilot.AgentRulesScopeTests` | PASS, 8/8; включая `test_stage_verdict_keeps_review_return_reason`. |
| API отдаёт причины возврата и fallback старой записи | `go test -count=1 ./internal/controlplane -run TestHTTPVerdictsReturnsEveryReviewReturnReason -v` | PASS; новая и старая причины возвращены, у успешного Review поле скрыто. |
| Экран показывает каждую одинаковую причину повторного возврата | `npm --prefix web test -- --run src/WorkView.test.tsx` | PASS, 4/4; две подписи причины присутствуют отдельно. |
| Смежные web-регрессии | чистый `npm ci`; полный Vitest, ESLint, typecheck, production build | PASS: 134/134, lint/typecheck/build без ошибок. |
| Смежные Go-регрессии | `go clean -testcache && go test -count=1 -timeout 10m ./...` | Затронутый `internal/controlplane` PASS (120.345 s); общий набор остановлен единственным отказом вне диффа: `internal/worker.TestIdleWorkerMakesOneClaimPerPollingInterval` не дождался условия за 5.48 s. |

`git diff --check origin/main...HEAD` чист; implementation commit существует, является предком ветки и меняет код вне `knowledge/cards/`.
