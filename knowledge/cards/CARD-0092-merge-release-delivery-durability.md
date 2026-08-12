# CARD-0092 — Durable-завершение выпуска после слияния

Implementation commit: 53e68a9274094ab0d83438603d626cad7714d7d7 — terminal-результат выпуска синхронизируется до публикации.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/bb9b6443-09c-a764c23f-183`.
- Implementation commit: 53e68a9274094ab0d83438603d626cad7714d7d7 — broker сохраняет accepted terminal status до ответа клиенту.
- What changed: файл операции и каталог `StateDirectory` синхронизируются после атомарной замены.
- What changed: restart читает accepted terminal status и не запускает executor повторно.
- Evidence: pinned `base_sha=9123aa42b01a39ce7f1fa998568189ab6d38b07b` и `candidate_sha=63fa612978e4d3ef8e62f01eeac7ce7b63f7a29d`; состав поставки — только broker, его тесты и карточка.
- Evidence: `go test -timeout 5m ./...` → PASS; `python3 -m unittest pilot.test_pilot` → 226 tests OK (13 skipped).
- Evidence: terminal persistence, restart recovery, no-repeat execution и lock retry покрыты тестами `internal/releasebroker`; `git diff --check` → PASS.
- Next action: human merge this verified release-boundary change.

## LOG

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Terminal-статус не публикуется до durable-записи | `go test -timeout 5m ./...`; targeted broker tests | PASS: при ошибке записи API и диск остаются в `running`, после restart операция становится `failed`, executor не повторяется. |
| Принятый выпуск переживает restart без повторного запуска | `go test -timeout 5m ./...` | PASS: accepted terminal status сохраняется, duplicate POST не запускает executor повторно. |
| Lock retry сохраняет идентичность | `go test -timeout 5m ./...` | PASS: повтор разрешён только для того же adapter/target с новым SHA; mutation отклоняется. |
| Регрессия проекта и Pilot | `python3 -m unittest pilot.test_pilot` | PASS: 226 tests OK, 13 skipped. |
| Pinned scope и чистота дерева | pinned `base...candidate`; `git diff --check`; `git status --short` | PASS: только broker, его тесты и карточка; diff clean, дерево чистое. |

### 2026-08-12 — Implement

Укреплена durable-граница release broker: terminal status публикуется только
после fsync файла операции и каталога состояния. Добавлен disk-backed restart
сценарий, доказывающий сохранение принятого статуса без второго физического
выпуска; целевые Python, Go и shell проверки прошли.
