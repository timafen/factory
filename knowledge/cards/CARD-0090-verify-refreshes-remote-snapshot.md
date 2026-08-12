# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

## HEAD

Status: PASS.
Branch: `factory/1a906a91-cdb-734c58dd-50b`.
Implementation commit: 14c6dfdb1355a1e03ac1a48c61ff87b42eebf44f — recovery и merge закреплены за SHA, прошедшим Verify.
What changed: recovery сверяет текущий head и слитый PR с SHA из merge intent. Merge использует атомарный `--match-head-commit`; force-push останавливает доставку.
Evidence: `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests pilot.test_pilot.ImmutableMergeTests pilot.test_pilot.MergeConflictRecoveryTests` — 11 tests OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — OK; `go build ./cmd/factory-server ./cmd/factory-worker ./cmd/factory-release-broker` — OK.
Next action: выполнить pinned Verify на опубликованных SHA после push.

## LOG

### 2026-08-12 — Implement

Перенесены изменения Verify на свежий `origin/main`: обновление удалённого снимка перед merge,
проверка неизменности delivery-ветки и целевые тесты на блокировку устаревшей поставки.
Целевые проверки прошли (6 tests OK), Go-бинарии собираются.

### 2026-08-12 — Implement

Закрыты две гонки после Review: recovery больше не принимает force-push или merge другого SHA,
а `gh pr merge` атомарно ограничен SHA из merge intent. Целевой набор из 11 тестов,
Python compile-check и сборка трёх Go-бинариев прошли.
