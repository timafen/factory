# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

## HEAD

Status: PASS.
Branch: `factory/ff76d242-9fb-59acb0b3-b0d`.
Implementation commit: 7aeeb7b10aede7f70985f9cd18c3d38fa21597b6 — Verify обновляет снимок кандидата и блокирует merge при force-push.
What changed: Verify получает свежие SHA основной и delivery-веток перед созданием merge intent. Merge повторно сверяет SHA кандидата до и после создания PR.
Evidence: `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests pilot.test_pilot.ImmutableMergeTests` — 6 tests OK; `go build ./cmd/factory-server ./cmd/factory-worker ./cmd/factory-release-broker` — OK.
Next action: выполнить pinned Verify на опубликованных SHA после push.

## LOG

### 2026-08-12 — Implement

Перенесены изменения Verify на свежий `origin/main`: обновление удалённого снимка перед merge,
проверка неизменности delivery-ветки и целевые тесты на блокировку устаревшей поставки.
Целевые проверки прошли (6 tests OK), Go-бинарии собираются.
