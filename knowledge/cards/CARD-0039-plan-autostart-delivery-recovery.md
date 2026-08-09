# CARD-0039 — Восстановление поставки автоподбора из Плана

## HEAD

- Status: BLOCKED — полный обязательный набор проверок не проходит из-за
  существующих сбоев вне поставки.
- Branch: `factory/7d59dbc9-8ee-3f833f88-27b`.
- Head commit: `1cdf0fb` — проверенный снимок восстановления на свежем `origin/main`.
- What changed: подтверждено, что реализация CARD-0034 уже вошла в свежий
  `origin/main` коммитом `c544784`; повторное изменение кода не требуется.
- Evidence: `python3 -m unittest -v pilot.test_pilot.PlanAutostartTest` —
  9 tests, OK; `go build ./...` — PASS. `just check` — BLOCKED:
  `staticcheck` сообщает 2 существующих нарушения в
  `internal/controlplane/cards_http.go` и `internal/controlplane/pilot_config.go`;
  UI-набор сообщает 3 падения в `web/src/Dialog.test.tsx` (98 из 101 прошли).
- Next action: устранить сбои `staticcheck` и `Dialog.test.tsx`, затем повторить Verify.

## LOG

### 2026-08-09 — Implement

После потери прежней ветки работа восстановлена от свежего `origin/main`.
Проверка истории показала, что функциональность уже слита как PR #20, поэтому
код не дублировался. Целевой набор прошёл: 32 теста, `OK`.
Сборка `go build ./...` также завершилась успешно.

### 2026-08-09 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| При свободном слоте стартует верхняя planned-карточка | `python3 -m unittest -v pilot.test_pilot.PlanAutostartTest` | PASS: `test_starts_top_planned_card_with_triage_context` и приоритет по `order` прошли. |
| Три независимые активные работы заполняют лимит | тот же целевой набор | PASS: `test_three_unique_active_or_owner_waiting_works_fill_slots` прошёл. |
| Повтор после неопределённого POST не создаёт дубликат | тот же целевой набор | PASS: `test_retry_after_uncertain_post_uses_same_card_request_key` прошёл. |
| Полный стандартный набор проекта | `just check`; затем `npm ci --prefix web` и `just ui-check` | BLOCKED: 2 нарушения `staticcheck`; UI-тесты — 3 падения, 98 из 101 прошли. |

Смежные проверки: `go build ./...`, форматирование, `go vet ./...` и граница
worker/control-plane прошли. Запущенный `go test -timeout 5m ./...` не завершился
в отведённое время, поэтому положительный результат ему не засчитан. Поставка по
трёхточечному сравнению содержит только эту карточку; `git diff --check
origin/main...HEAD` чист.
