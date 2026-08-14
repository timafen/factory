Implementation commit: 051316a3c410aeb1e1d9c0e44ab7753fdc4ae76a — текущая база содержит проверку безопасных стартовых состояний ворот выпуска.

# CARD-0163 — Восстановление отставшей ветки поставки

## Статус

Specification. Реализация не выполнялась на этом этапе.

## Контекст

Проверка поставки фиксирует remote default branch и candidate SHA, но большой
разрыв между ними способен скрыть все обещанные файлы реализации в текущем
diff. Нужна безопасная пересборка delivery-ветки из подтверждённой реализации,
а не повторная разработка или слияние непроверенной вершины.

## Решение

Pilot пересобирает только stale delivery от свежей remote-основы и только по
promised paths canonical implementation artifact, затем повторно закрепляет
ветку перед Review. Read-only promises API объясняет оператору обещания и
обязательную проверку. Полный план и критерии: `knowledge/specs/stale-delivery-branch-reconciliation.md`.

## Область следующей реализации

- `pilot/pilot.py`
- `pilot/test_pilot.py`
- `internal/controlplane/promises_http.go`
- `internal/controlplane/http_test.go`

## Проверка

`python3 -m unittest -v pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests`
