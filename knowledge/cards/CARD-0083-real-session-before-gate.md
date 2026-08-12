# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting repeat review.
Branch: factory/d3645519-0ac-53f5753d-417.
Implementation commit: 72ec617f7661fbfbbc10150765da8217ba508bf9 — Gate извлекает полный проверенный набор и хранится вне доступного пользователю каталога релизов.
What changed: защищённая копия содержит Gate, release helper, `systemd/`, broker installer, `fx`, `pilot/` и `intake/` из одного Git commit с проверкой каждого blob.
What changed: временный Gate создаётся в root-owned `0700` родителе; конкурентная подмена в доступном `$REL` не находит цели.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS, включая настоящий извлечённый Gate и конкурентную попытку подмены.
Evidence: `npm --prefix web run typecheck`, `npm --prefix web run build`, `go test ./...`, Go builds и `git diff --check` → PASS.
One next action: repeat human review of the trusted-copy Gate.

## LOG

### 2026-08-12 — Implement

После повторного review Gate извлекает полный набор своих относительных
ресурсов из проверяемых Git blob одного commit. Временная копия перенесена из
доступного пользователю каталога релизов в закрытый root-owned родительский
каталог. Полный shell-suite выполнил настоящий извлечённый Gate во время
конкурентной попытки подмены; typecheck, UI build, Go tests/build и diff check прошли.

### 2026-08-12 — Implement

После замечания review защищённый каталог Gate дополнен соседним
`fx-factory-release` и полным деревом `systemd/`, извлечёнными из тех же
проверяемых Git blob. Новый интеграционный сценарий запускает именно извлечённый
`ops/test-fx-factory-release.sh`, подтверждает наличие относительных ресурсов и
отмечает выполнение только после handshake; shell-suite, Bash syntax и diff check прошли.

### 2026-08-11 — Implement

Защита перенесена поверх свежего `main`, а недоверенный gate-файл заменён
криптографически проверенной копией из commit object в закрытом каталоге.
Adversarial fixture меняет рабочий сценарий на `exit 0`: выпуск сохраняет настоящий
отказ `5` и не начинает build/install. Release-suite, Go test/build, UI build,
shell syntax и diff check прошли; единичный UI timeout вне scope прошёл retry 3/3.

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
