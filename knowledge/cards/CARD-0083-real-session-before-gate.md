# CARD-0083 — Реальная session подтверждает gate до установки

Implementation commit: 8f8e701263be9ceba44f07c2f6fa80f167f8e9e8 — release gate подтверждает реальную session до запуска проверок.

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/6e66d8d8-0a6-a1f9f952-aa7.
Implementation commit: 8f8e701263be9ceba44f07c2f6fa80f167f8e9e8 — release gate подтверждает реальную session до запуска проверок.
What changed: wrapper атомарно сообщает свой SID/PGID до `$AS`, UI и Go gate; выпуск ждёт именно эту группу.
What changed: cleanup завершает подтверждённую process group, а неготовый launcher останавливает отдельно.
Evidence: `bash ops/test-fx-factory-release.sh`, `npx tsc -p tsconfig.app.json --noEmit`, UI-тесты/сборка и `go test ./...` → PASS.
One next action: merge the implementation branch.

## LOG

### 2026-08-11 — Implement

Forked launcher больше не считается результатом gate: готовность подтверждается
только wrapper из реальной session, ещё до старта проверок. Shell-фикстура
принудительно форкает `setsid` и подтверждает, что успешный выпуск ждёт рабочую
группу, а отказ gate не устанавливает новые бинарные файлы.
