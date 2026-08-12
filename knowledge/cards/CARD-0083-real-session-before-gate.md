# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/5d250fde-09f-9cbb7136-05f.
Implementation commit: 741c717ecbf8fc96bb0b3de079c8bbde1a250820 — вся release-цепочка закреплена абсолютными tools, каждый gate изолирован cgroup v2.
What changed: безопасный root PATH устанавливается до первого external command; checkout, lock, ownership, gates, installation и cleanup используют проверенные абсолютные executables.
What changed: gate останавливается до attach в отдельную cgroup; успех требует пустой cgroup, остатки получают bounded TERM→KILL и приводят к отказу без install.
Preserved: root-owned immutable checkout, абсолютный Node, SID/PGID/supervisor/nonce, signal cleanup, kernel wait status и запрет install до двух gates; Pilot выключен.
Evidence: hostile PATH и real escaped-setsid/fork/fail/signal shell-suite ×3 → PASS; live процессов и install не осталось.
Evidence: `go test ./...`, `go build ./...`, 157 UI tests/build, `bash -n`, `git diff --check` → PASS.
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

### 2026-08-11 — Implement

Итоговая защита перенесена без промежуточных изменений на `main`
`60cba840f39a453862c1c0f87f261fd453b09688` отдельным implementation-коммитом.
Три shell-прогона, полный Go test/build, 157 UI-тестов, UI build, `bash -n`
и `git diff --check` прошли; scope относительно свежей базы ограничен этой карточкой
и двумя gate-скриптами. Pilot не включался.

### 2026-08-11 — Implement

Security correction перенесена на свежий `main` `36ce322e2b6685dd9a87f4d2c947f61538654ae1`:
gate читает root-owned замороженный checkout, не допускает caller-controlled `$AS`,
а UI использует абсолютные Node/npm/npx с очищенным PATH. Успешный gate с реальным
фоновым потомком ограниченно проходит TERM→KILL/reap и превращается в отказ без
установки. Расширенный shell-suite ×2, Go build, 157 UI tests/build и syntax/diff прошли;
полный Go test повторил существующий на `origin/main` отказ схемы поля CARD-0087.

### 2026-08-11 — Implement

Security correction перенесена на зелёный `main` `3183424f924d440b686908f219d0013b7ee8c504`.
Release устанавливает безопасный PATH до первого external command и валидирует абсолютные
tools для checkout, lock, ownership, gates, установки и cleanup. Root launcher сначала
останавливается, входит в отдельную cgroup v2 и только затем запускает `setsid`; escaped
session очищается bounded TERM→KILL, делает gate неуспешным и не допускает install.
Shell-suite ×3, полный Go test/build, 157 UI tests/build, syntax/diff прошли; Pilot не включён.
