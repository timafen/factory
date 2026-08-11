# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/7e7934c4-112-7ab1b699-725.
Implementation commit: 0fdcbcc5148495bde3f579562e818b12efc362f7 — launcher исключён из решения о результате gate.
What changed: gate запускается в требуемой identity только фиксированным root-owned `/usr/bin/sudo`; `$AS` не получает result path и не входит в цепочку доверия.
What changed: одноразовый результат — kernel wait status цепочки `setsid --wait → sudo → gate`; файловый running/finished protocol полностью удалён.
Threat model: произвольный fork-capable `$AS` того же UID знает прежний путь и может атомарно писать valid/corrupt/stale/replayed status, но эти файлы больше не читаются.
Evidence: spoofed `status=0` + реальный gate `1` → release `5`, install events `0`; fork-success → install `1`; shell-suite ×3 → PASS.
Evidence: `go test -timeout 5m ./...`, `go build ./...`, `cd web && npm ci && npm run build`, `git diff --check` → PASS.
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
