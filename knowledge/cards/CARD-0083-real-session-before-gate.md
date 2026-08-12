# Реальная session регистрируется до запуска gate

Implementation commit: 947b75529ffa7b81fb10092e63c4897161ca8ae2 — release gate подтверждает реальную session до запуска проверок.

## HEAD

Status: BLOCKED: verification — release shell scenario does not complete.
Branch: factory/8a3074e0-07e-b8f274f9-77e.
Implementation commit: 947b75529ffa7b81fb10092e63c4897161ca8ae2 — release gate подтверждает реальную session до запуска проверок.
What changed: session wrapper атомарно сообщает свой SID/PGID до `$AS`, UI и Go gate; выпуск ожидает именно эту группу.
What changed: cleanup завершает подтверждённую process group; неготовый launcher останавливается отдельно.
Evidence: pinned candidate was checked against remote `main`; `bash ops/test-fx-factory-release.sh` did not complete and was terminated by a 45-second limit, leaving `fx-factory-release` active.
One next action: fix the hanging gate scenario and rerun verification.

## LOG

### 2026-08-11 — Implement

Forked launcher больше не считается session gate: готовность подтверждается только
из wrapper, уже запущенного через `setsid`, до старта проверок. Shell-фикстура
принудительно форкает launcher и подтверждает успешный выпуск без потери реальной
группы; signal-cleanup и отказавшие gate-сценарии сохранены.

### 2026-08-12 — Verify

| Критерий | Проверка | Наблюдение |
| --- | --- | --- |
| Реальная session подтверждается до запуска gate | анализ pinned diff и shell-фикстуры с forked `setsid` | реализован handshake `sid`/`pgid` до исполнения gate |
| Сценарий release gate завершается | `timeout --kill-after=5s 45s bash ops/test-fx-factory-release.sh` | не завершился; timeout остановил активный `fx-factory-release` (`Terminated`) |
| Карточка ссылается на кодовую реализацию | `merge-base --is-ancestor` и `diff-tree` | commit реализации — предок ветки и меняет оба shell-файла |
