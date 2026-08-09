# CARD-0039 — Восстановление поставки автоподбора из Плана

## HEAD

- Status: Verified PASS — ожидает решения человека о слиянии.
- Branch: `factory/eac4fd1b-8c2-eb36317b-da2`.
- Head commit: `667639b` — проверенный снимок реализации на свежем `origin/main`.
- What changed: подтверждено, что реализация CARD-0034 уже вошла в свежий
  `origin/main` коммитом `c544784`; повторное изменение кода не требуется.
- Evidence: `python3 -m unittest -v pilot.test_pilot.PlanAutostartTest` —
  9 tests, OK; `go build ./...` — PASS. Независимый техдолг вынесен в
  CARD-0040: `just check` сообщает
  `staticcheck` сообщает 2 существующих нарушения в
  `internal/controlplane/cards_http.go` и `internal/controlplane/pilot_config.go`;
  UI-набор сообщает 3 падения в `web/src/Dialog.test.tsx` (98 из 101 прошли).
- Next action: человеку принять решение о слиянии; CARD-0040 исправить отдельно.

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

### 2026-08-09 — Verify (решение владельца)

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Верхняя planned-карточка запускается | `python3 -m unittest -v pilot.test_pilot.PlanAutostartTest` | PASS: 9 из 9, включая выбор верхней по `order`. |
| Лимит трёх работ соблюдается | тот же набор | PASS: три уникальные активные работы заполняют слоты. |
| Повторный POST идемпотентен | тот же набор | PASS: повтор использует прежний request key. |
| Сборка соседнего Go-кода | `go build ./...` | PASS, код 0. |
| Полные проектные ворота | `just check`; `npm ci --prefix web && just ui-check`; `timeout 6m go test ./...` | Go-набор PASS; независимый долг принят владельцем: 2 нарушения `staticcheck` и 3 падения `Dialog.test.tsx`. Вынесено в CARD-0040. |

По утверждённому решению владельца системные сбои полного набора не блокируют
эту поставку и не требуют нового круга Verify. Реализация автоподбора находится
в `main`; ветка проверки содержит только карточки с доказательствами.
