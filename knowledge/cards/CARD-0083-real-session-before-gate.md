# Реальная session gate не подменяется через PATH

## HEAD

Status: Implemented — awaiting human merge.
Implementation commit: ffcaeb87607798898d807bdf416aa5167f102767 — доверенная цепочка gate закреплена абсолютными системными путями.
Branch: factory/3f6b4aad-25e-c8aab9c3-1d0.
What changed: gate запускается через проверенные root-owned `/usr/bin/setsid`, `/bin/bash` и `/usr/bin/sudo`, независимо от `PATH` и `$AS`.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS; вредоносный `setsid` из `PATH` не вызывается, failing gate возвращает `5`, установки и перезапуска нет.
One next action: merge the branch.

## LOG

### 2026-08-11 — Implement

Закрыта PATH-подмена доверенной цепочки. Adversarial-фикстура помещает в `PATH`
`setsid`, который при запуске создаёт правдоподобный PID-handshake и возвращает
успех, не запуская gate. Релиз игнорирует этот файл, ждёт настоящий gate и при
его ошибке не устанавливает новые бинарники и не трогает службы. Целевой suite
также повторяет cleanup и сценарии forked gate.
