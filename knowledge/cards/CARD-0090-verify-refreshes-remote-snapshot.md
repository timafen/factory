# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

## HEAD

Status: PASS.
Branch: `factory/a62f2494-33b-09586b53-ed1`.
Implementation commit: c4fe862207c73b497bb24afa109d4dd32c47821e — пустая закреплённая поставка возвращается до Review, сравнение использует точные base и candidate SHA.
What changed: Review и Verify закрепляют свежие удалённые SHA; пустой pinned diff возвращает реализацию одним сообщением. Все сравнения области выполняются как `base_sha...candidate_sha`.
Evidence: `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests` — 5 tests OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — OK; `git diff --check` — OK.
Next action: повторить Review опубликованной ветки.

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

После замечаний Review пустой закреплённый diff теперь возвращает работу в разработку
одним сообщением, а область вычисляется строго по `base_sha...candidate_sha`.
Целевой класс из 5 тестов, compile-check и проверка diff прошли.
