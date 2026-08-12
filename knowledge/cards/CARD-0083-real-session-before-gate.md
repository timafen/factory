# Реальная session gate не подменяется через PATH

## HEAD

Status: Implemented — awaiting review.
Implementation commit: a818cec94e1f771ecf3a604635cf302694db53f5 — UI- и Go-gate входят через `/usr/bin/sudo -H -u factory` до `/usr/bin/setsid --wait`.
Branch: factory/e1d7b175-f3b-0400f866-21f.
What changed: gate выполняются ограниченным пользователем `factory`; `$AS` больше не определяет их identity. Системный `setsid` остаётся закреплённым и передаёт код gate через kernel wait.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` → PASS; целевой fixture-suite проверяет `factory`, непустой `FACTORY_RELEASE_AS` и PATH-spoof `setsid`.
One next action: run review and merge after PASS.

## LOG

### 2026-08-11 — Implement

Закрыта PATH-подмена доверенной цепочки. Adversarial-фикстура помещает в `PATH`
`setsid`, который при запуске создаёт правдоподобный PID-handshake и возвращает
успех, не запуская gate. Релиз игнорирует этот файл, ждёт настоящий gate и при
его ошибке не устанавливает новые бинарники и не трогает службы. Целевой suite
также повторяет cleanup и сценарии forked gate.

### 2026-08-12 — Implement

Исправлен review-блокер: каждая группа UI/Go-проверок теперь запускается строго
через root-owned `/usr/bin/sudo -H -u factory` перед `/usr/bin/setsid --wait`.
Фикстура с непустым `FACTORY_RELEASE_AS` подтверждает identity `factory`, а
отдельная PATH-подмена `setsid` по-прежнему не запускается.
