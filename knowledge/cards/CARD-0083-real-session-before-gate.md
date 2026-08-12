# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/6c7e734d-75e-4a53d483-d59.
Implementation commit: d0ed8773a2376da50f9420f60ef559ef511584bb — Gate запускается из закрытой копии, извлечённой и проверенной по Git blob SHA.
What changed: handshake/session cleanup перенесены на свежий `main`; `$AS` исключён из цепочки запуска и результата.
What changed: gate-сценарий извлекается из commit object в каталог mode `0700`, сверяется через `git hash-object` и запускается оттуда.
Threat model: замена рабочего `ops/test-fx-factory-release.sh` после checkout не может превратить настоящий отказ Gate в успех.
Evidence: workspace gate заменён на `exit 0` → доверенная копия вернула release `5`, сборка/установка не начались; полный release shell-suite → PASS.
Evidence: `go test -timeout 5m ./...`, `go build ./...`, UI build, `bash -n`, `git diff --check` → PASS; один UI timeout вне scope прошёл точечный retry (3/3).
One next action: human merge into main.

## LOG

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
