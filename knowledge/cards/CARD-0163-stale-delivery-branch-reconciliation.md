# CARD-0163 — Восстановление отставшей ветки поставки

## HEAD

Status: Implemented.
Branch: `factory/ad044976-a42-1deed0bd-550`.
Implementation commit: cd9a483893a11fcecfaa5b3e7538fae4f53830a2 — отставшая поставка пересобирается из подтверждённой реализации только по promised paths.
What changed: Review заново закрепляет rebuilt delivery перед продолжением конвейера; promises API показывает статус пересборки без служебных Git-данных.
Evidence: `python3 -m unittest -v pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests` → OK (11 tests); `go test ./internal/controlplane` → OK.
Next action: Review проверить поставку по новому pinned candidate.

## LOG

### 2026-08-14 — Specification

Проверка поставки фиксирует remote default branch и candidate SHA, но большой
разрыв между ними способен скрыть все обещанные файлы реализации в текущем
diff. Нужна безопасная пересборка delivery-ветки из подтверждённой реализации,
а не повторная разработка или слияние непроверенной вершины.

Pilot пересобирает только stale delivery от свежей remote-основы и только по
promised paths canonical implementation artifact, затем повторно закрепляет
ветку перед Review. Read-only promises API объясняет оператору обещания и
обязательную проверку. Полный план и критерии: `knowledge/specs/stale-delivery-branch-reconciliation.md`.

### 2026-08-14 — Implement

Review восстанавливает только отставшую delivery-ветку из совпадающего с
артефактом implementation SHA и заново закрепляет результат; ошибка fetch
блокирует конвейер без возврата в Implement. Статус доступен в read-only
promises API. Целевые Python-проверки (11) и `go test ./internal/controlplane` прошли.
