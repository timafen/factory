# Реальная session регистрируется до запуска gate

Implementation commit: 947b75529ffa7b81fb10092e63c4897161ca8ae2 — release gate подтверждает реальную session до запуска проверок.

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/8a3074e0-07e-b8f274f9-77e.
Implementation commit: 947b75529ffa7b81fb10092e63c4897161ca8ae2 — release gate подтверждает реальную session до запуска проверок.
What changed: session wrapper атомарно сообщает свой SID/PGID до `$AS`, UI и Go gate; выпуск ожидает именно эту группу.
What changed: cleanup завершает подтверждённую process group; неготовый launcher останавливается отдельно.
Evidence: `bash ops/test-fx-factory-release.sh`, включая forked `setsid` → PASS; Go tests/build и web typecheck/tests/build → PASS.
One next action: merge the implementation branch.

## LOG

### 2026-08-11 — Implement

Forked launcher больше не считается session gate: готовность подтверждается только
из wrapper, уже запущенного через `setsid`, до старта проверок. Shell-фикстура
принудительно форкает launcher и подтверждает успешный выпуск без потери реальной
группы; signal-cleanup и отказавшие gate-сценарии сохранены.
