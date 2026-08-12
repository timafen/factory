# CARD-0083 — Реальная session подтверждает gate до установки

Implementation commit: acd440dc7ab336b894ff1c7d6c85f08b1946b5a1 — ошибка настоящего gate запрещает установку.

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/102792ba-365-f6cb456c-118.
Implementation commit: acd440dc7ab336b894ff1c7d6c85f08b1946b5a1 — ошибка настоящего gate запрещает установку.
What changed: реальная session атомарно записывает SID, PGID и код завершения в отдельный result-файл.
What changed: выпуск продолжается только при явном `status=0`; отсутствие результата или чужая session завершают release до установки.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` → PASS; регрессия `forked-gate-fail` проверяет forked `setsid` и отсутствие изменений служб/бинарников.
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
