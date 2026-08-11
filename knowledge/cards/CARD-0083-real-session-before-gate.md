# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/b3052294-9b9-63503efd-ec9.
Implementation commit: d6cda20403b9f72494c7cbf4b20decd16ccbae17 — вся gate-цепочка закреплена за проверенными абсолютными путями и живой session.
What changed: `/usr/bin/setsid --fork --wait → /usr/bin/sudo → /bin/bash → абсолютный gate script`; системные executables проверяются как root-owned и не writable для group/other.
What changed: nonce-handshake принимается только от живого session leader — прямого ребёнка запущенного supervisor; gate ждёт одноразовый ack, а итогом остаётся kernel wait status.
Threat model: PATH/function/alias/env/config shadow, prewritten/replayed/forged handshake и исчезнувшая PGID не могут дать успех; `$AS` исключён из цепочки результата.
Evidence: malicious PATH `setsid` с `sid=999999 pgid=999999 ready=1` + `0`, forged file и missing session → release `5`, installs/restarts/build replacements `0`; real fork fail/success и signal cleanup → PASS; shell-suite ×3 → PASS.
Evidence: `go test -timeout 5m ./...`, `go build ./...`, `cd web && npm ci && npm test && npm run build`, `bash -n`, `git diff --check` → PASS.
One next action: human merge into main.

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
