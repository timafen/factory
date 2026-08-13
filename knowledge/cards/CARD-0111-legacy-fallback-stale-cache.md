# CARD-0111: усилить legacy fallback и fixture stale-cache

## HEAD

Status: Verified PASS — awaiting human merge
Branch: `factory/d8a17c2c-94c-973bb42e-a68`
Implementation commit: 1a40e53674cc211b4f274b92c6bac4aeca98311f — Review блокирует невалидную identity и проверяет stale-cache через pinned SHA.
Evidence: пять целевых проверок Review/stale-cache → OK; `python3 -m unittest -q pilot.test_pilot` имеет 2 одинаковых с main сбоя в `CorrectionProvenanceStormTests`; `just check` останавливается на одинаковом с main SA4000 в `internal/worker/attempt_lifecycle_test.go:31`.
One next action: human merge after accepting the documented pre-existing project-check failures.

## LOG

### 2026-08-12 — Implement

Изменён `pilot/pilot.py`: Review теперь fail-closed для отсутствующей или невалидной repository identity и не вызывает legacy `branch_report` как authoritative fallback. В `pilot/test_pilot.py` добавлена stale-cache fixture с observer, клонированным до продвижения remote main, и проверкой pinned scope. Целевой тест и `git diff --check` зелёные; первый полный Pilot-набор выявил несовместимые старые seam-тесты, которые были обновлены в той же поставке.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Review не использует legacy fallback | diff pinned `35a8618...befb8b5`; 5 целевых `unittest` | `review_gate` возвращает BLOCKED при ошибке инфраструктуры; 5/5 OK |
| Stale cached main не задаёт scope | `FreshDefaultBranchSnapshotTests.test_stale_cached_main_never_defines_review_scope` | fixture закрепляет свежий remote base и видит только `delivery.txt` |
| Смежные ошибки не маскируются | полный `python3 -m unittest -q pilot.test_pilot` на candidate и main | по 2 одинаковых failure в `CorrectionProvenanceStormTests` |
| Нормальный project check | `just check` на candidate и main | по одному одинаковому SA4000 в неизменённом `internal/worker/attempt_lifecycle_test.go:31` |
