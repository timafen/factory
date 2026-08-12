# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/92c05a1d-a0a-437ef620-ec1.
Implementation commit: 71baa59ef6efb819ee32db163347235a7ef6b4c3 — checkout и gate inputs изолированы от `$AS`, Node закреплён абсолютно, drain process group ограничен.
What changed: `/usr/bin/git` получает исходники в root-owned read-only snapshot; нестандартный `$AS` отклоняется до checkout/gate/install.
What changed: UI запускается через проверенные `/usr/bin/node` и абсолютные npm/npx entrypoints с `PATH=/usr/bin:/bin`; успешный gate с потомком получает bounded TERM→KILL, reap и failure.
Preserved: абсолютные trusted tools, live SID/PGID/supervisor/nonce handshake, signal cleanup, kernel wait result и запрет production install до обоих gates; Pilot не включён.
Evidence: hostile `$AS`/checkout, fake `PATH/node`, real orphan, fork/fail/signal suite ×2 → PASS; процессов и install не осталось.
Evidence: `go build ./...`, `cd web && npm ci && npm test && npm run build`, `bash -n`, `git diff --check` → PASS; `go test ./...` повторяет baseline CARD-0087 schema failure.
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
