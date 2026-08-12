# CARD-0083 — Реальная session подтверждает gate до установки

Implementation commit: e4599a2bb94236daf55863a20b8db1a79029f641 — ошибка настоящего gate запрещает установку.

## HEAD

Status: Implemented and integration-tested — awaiting human merge.
Branch: factory/7c458632-327-af60df60-b9f.
Implementation commit: e4599a2bb94236daf55863a20b8db1a79029f641 — ошибка настоящего gate запрещает установку.
What changed: реальная session атомарно записывает SID, PGID и код завершения в отдельный result-файл.
What changed: выпуск продолжается только при явном `status=0`; отсутствие результата или чужая session завершают release до установки.
Evidence: `ops/test-fx-factory-release.sh` → PASS в изолированной временной фикстуре; `forked-gate-fail` проверяет forked `setsid` и отсутствие изменений служб/бинарников.
One next action: merge the implementation branch.

## LOG

### 2026-08-11 — Implement

Forked launcher больше не считается результатом gate: готовность подтверждается
только wrapper из реальной session, ещё до старта проверок. Shell-фикстура
принудительно форкает `setsid` и подтверждает, что успешный выпуск ждёт рабочую
группу, а отказ gate не устанавливает новые бинарные файлы.

### 2026-08-12 — Implement

Результат настоящего gate теперь передаётся отдельным атомарным файлом из его
реальной session. Только явный нулевой код позволяет перейти к установке;
исчезновение process group либо отсутствие результата считаются отказом.
Добавлен отказ UI gate за forked `setsid`-launcher с проверкой прежних бинарников
и отсутствия перезапуска служб. Синтаксис обоих shell-скриптов проверен `bash -n`.

### 2026-08-12 — Implement

Полный `ops/test-fx-factory-release.sh` успешно выполнен в изолированной временной
фикстуре с отдельными process sessions. Сценарии `ui-test-fail`, `go-test-fail`,
`release-test-fail` и `forked-gate-fail` подтвердили код ошибки 5, прежние бинарники
и отсутствие перезапуска служб; дополнительно проверены rollback и signal-пути.
