# CARD-0092 — Durable-завершение выпуска после слияния

Implementation commit: 9edebf6467289614d5d347c6bf37475b0104af0f — terminal-результат выпуска синхронизируется до публикации.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/90ca3d85-905-a7b41954-738`.
- Implementation commit: 9edebf6467289614d5d347c6bf37475b0104af0f — broker сохраняет accepted terminal status до ответа клиенту.
- What changed: файл операции и каталог `StateDirectory` синхронизируются после атомарной замены.
- What changed: restart читает accepted terminal status и не запускает executor повторно.
- Evidence: `go test ./internal/releasebroker` → OK; `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` → 10 OK; оба shell-теста release driver → OK.
- Next action: выполнить общий `just check` на этапе Verify.

## LOG

### 2026-08-12 — Implement

Укреплена durable-граница release broker: terminal status публикуется только
после fsync файла операции и каталога состояния. Добавлен disk-backed restart
сценарий, доказывающий сохранение принятого статуса без второго физического
выпуска; целевые Python, Go и shell проверки прошли.
