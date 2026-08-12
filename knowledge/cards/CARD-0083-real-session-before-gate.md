# Реальная session регистрируется до запуска gate

Implementation commit: be58e8096302044be7e96ee96a9e32aef93ddd08 — Node закреплён абсолютным путём, а release self-test больше не запускает себя рекурсивно.

## HEAD

Status: Implemented — gate criteria PASS; merge waits for the unrelated browser regression to become green.
Branch: factory/4c92c207-803-93fc28aa-d9e.
Implementation commit: be58e8096302044be7e96ee96a9e32aef93ddd08 — Node закреплён абсолютным путём, а release self-test больше не запускает себя рекурсивно.
What changed: UI gate invokes trusted `npm`/`npx` scripts through validated `/usr/bin/node`; a caller-controlled `PATH/node` cannot supply the runtime.
What changed: the cloned release fixture contains a bounded gate stub, so the outer self-test validates nested success/failure without recursively starting its whole driver.
Evidence: trusted-Node PATH-probe → `npm=1`, `npx=1`, shebang control `=0`; `timeout 300 bash ops/test-fx-factory-release.sh` → PASS in 150s.
Evidence: UI (158 tests), embedded UI, tooling, build, release, launcher, format, vet, vuln, staticcheck, boundary, Go and worker race → PASS.
Known finding: unchanged browser HTTPS pause/resume scenario expects `работа завершена`, while main renders `ждёт подтверждённый выпуск`; full and targeted browser runs fail outside gate scope.
One next action: resolve the browser contract on its own task, rerun that tail, then merge.

## LOG

### 2026-08-11 — Implement

Реальный wrapper после `setsid` записывает SID, PGID и ready атомарной заменой файла,
до запуска `$AS` и UI/Go gate. Shell-фикстуры принудительно форкают GNU `setsid` и
посредник `$AS`, отправляют HUP/INT/TERM до и после readiness, оставляют дочерние
процессы игнорировать TERM и подтверждают bounded cleanup, отсутствие процессов и
отсутствие production install. Полный shell-тест, Go test/build и UI production build прошли.

### 2026-08-11 — Implement

Forking `$AS`, возвращающий 0 до конца gate, больше не скрывает ошибку настоящей
команды: её wrapper атомарно публикует финальный status, а session-supervisor ждёт
его с bounded fail-closed semantics. Adversarial shell-сценарии подтвердили успех
forked gate, отказ с точным `status=1`, запрет установки, отсутствие потомков и
отказ при пропавшем результате; прежние readiness/signal проверки сохранены.
Shell-suite прошёл трижды, Go test/build и UI production build прошли.

### 2026-08-11 — Implement

Строгая модель угроз признала прежний файл недоверенным: `$AS` работает с тем же UID,
знает путь и может атомарно заменить даже синтаксически правильный `status=0`.
Файловый result protocol удалён; gate теперь идёт через фиксированный root-owned
identity launcher, а supervisor принимает только kernel wait status этой цепочки.
Тестовый fork-capable `$AS` записал stale, corrupt, valid и replayed success до
настоящего `exit 1`: выпуск вернул 5, не установил ничего и не оставил процессов.

### 2026-08-11 — Implement

Review-воспроизведение показало PATH bypass: подменённый `setsid` мог записать
правдоподобный, но несуществующий SID/PGID и вернуть `0`. Gate-цепочка теперь
использует только проверенные абсолютные executables, а nonce/ack доказывает живую
session и её прямую связь с конкретным `setsid --fork --wait` supervisor до старта
gate. PATH-shadow, forged/prewritten handshake, missing session, real fork fail/success
и HUP/INT/TERM cleanup прошли shell-suite трижды; Go test/build и UI test/build зелёные.

### 2026-08-12 — Implement

UI gate теперь передаёт проверенные `npm` и `npx` закреплённому абсолютному Node,
поэтому подложенный `PATH/node` больше не превращает невозможную команду в успех.
Вложенный release gate в фикстуре заменён bounded stub: целевой self-test завершился
с PASS за 150 секунд без рекурсивного роста процессов. Полный Verify зелёный до
неизменённого browser-контракта pause/resume; его отдельный повтор воспроизвёл дефект main.
