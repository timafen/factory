# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

## HEAD

Status: PASS.
Branch: `factory/96cb138f-2fa-641c94ee-0d0`.
Implementation commit: 7bbde9e8dd58866f64631fffce1735df1b38c35d — Review сохраняет SHA пересобранной delivery-ветки, а Verify сверяет и сливает именно его.
What changed: delivery artifact теперь содержит закреплённые branch и head. После rebuild новый remote-снимок фиксируется до Review; Verify больше не сравнивает пересобранную ветку с SHA исходной реализации.
Evidence: целевой набор — 11 tests OK; `python3 -m unittest pilot.test_pilot` — 237 tests OK (13 skipped); `go test ./...` и сборка трёх Go-бинариев — OK.
Next action: повторить Review для опубликованной ветки.

## LOG

### 2026-08-12 — Implement

Перенесены изменения Verify на свежий `origin/main`: обновление удалённого снимка перед merge,
проверка неизменности delivery-ветки и целевые тесты на блокировку устаревшей поставки.
Целевые проверки прошли (6 tests OK), Go-бинарии собираются.

### 2026-08-12 — Implement

Закрыты две гонки после Review: recovery больше не принимает force-push или merge другого SHA,
а `gh pr merge` атомарно ограничен SHA из merge intent. Целевой набор из 11 тестов,
Python compile-check и сборка трёх Go-бинариев прошли.

### 2026-08-12 — Implement

Устранён цикл после успешного Review: SHA пересобранной delivery-ветки сохраняется отдельно
от SHA исходной реализации и проходит через Verify в merge intent. Регрессионный pipeline-тест
использует разные SHA и подтверждает merge именно delivery SHA; полный Python- и Go-набор зелёный.
