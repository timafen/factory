Implementation commit: 58d937492487b9e92c06155ec28d6151214a5f65 — строгая проверка дат, независимые лимиты групп и честный значок провалов в исходной работе.

# CARD-0101 — «Сделано недавно»: влитое отдельно и даты по-человечески

## HEAD

- Status: Specification.
- Branch: `factory/32bf2526-114-6034011d-56c`.
- Specification: `knowledge/specs/recent-done-merged-failures-human-dates.md`.
- Scope: control-plane API-классификация, Pilot recent-done и Overview.
- Required check: `python3 -m unittest -v pilot.test_pilot.RecentDoneTest.test_separates_merged_and_failed_with_independent_limits`.

## LOG

### 2026-08-14 — Specification

Продолжена исходная CARD-0101 на свежем `origin/main`. Предыдущая реализация
разделяла слияния и провалы, но её title-фильтр служебных задач не защищает от
регулярной Automation и может неверно скрыть пользовательский «патруль».

Определён единый источник: server-computed `work_class` из durable связи task с
Automation и schedule. Pilot не классифицирует по заголовку. Receipt остаётся
единственным доказательством влития; `merged` и `failed` лимитируются отдельно,
а failures показывают этап и причину. Overview отображает локальные даты и
очередь человеческими словами.
