# CARD-0111: усилить legacy fallback и fixture stale-cache

Implementation commit: e6c884a4387b92e3059d1385cc84a3bc22c95c3b — Review использует свежий pinned snapshot, блокирует невалидную repository identity и проверяет stale-cache; [фактическая поставка Review](https://github.com/timafen/factory/commit/e6c884a4387b92e3059d1385cc84a3bc22c95c3b) влита в `main` через PR #207.

## HEAD

Status: Done — merged into `main` via PR #207 on 2026-08-13
Evidence: фактический implementation commit входит в свежий `origin/main`; шесть целевых `FreshDefaultBranchSnapshotTests` → OK.
One next action: none; повторную поставку закрыть как `CLOSE / DUPLICATE`.

## LOG

### 2026-08-13 — Documentation cleanup

После решения владельца карточка приведена к фактическому состоянию: защита уже
влита в `main` через PR #207. Устаревшие предсливочный статус, ветка и ссылка на
промежуточный SHA заменены ссылкой на merged implementation commit. Повторная
разработка не требуется.

### 2026-08-12 — Implement

Изменён `pilot/pilot.py`: Review теперь fail-closed для отсутствующей или невалидной repository identity и не вызывает legacy `branch_report` как authoritative fallback. В `pilot/test_pilot.py` добавлена stale-cache fixture с observer, клонированным до продвижения remote main, и проверкой pinned scope. Целевой тест и `git diff --check` зелёные; первый полный Pilot-набор выявил несовместимые старые seam-тесты, которые были обновлены в той же поставке.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Review не использует legacy fallback | diff pinned `35a8618...befb8b5`; 5 целевых `unittest` | `review_gate` возвращает BLOCKED при ошибке инфраструктуры; 5/5 OK |
| Stale cached main не задаёт scope | `FreshDefaultBranchSnapshotTests.test_stale_cached_main_never_defines_review_scope` | fixture закрепляет свежий remote base и видит только `delivery.txt` |
| Смежные ошибки не маскируются | полный `python3 -m unittest -q pilot.test_pilot` на candidate и main | по 2 одинаковых failure в `CorrectionProvenanceStormTests` |
| Нормальный project check | `just check` на candidate и main | по одному одинаковому SA4000 в неизменённом `internal/worker/attempt_lifecycle_test.go:31` |
