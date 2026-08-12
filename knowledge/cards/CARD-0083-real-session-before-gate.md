# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting Review.
Branch: factory/bb8ca82f-c03-f449cc1a-339.
Implementation commit: cb044f70023a9ece1f33531f14c86adc261c3958 — gate запускается через проверенный абсолютный `/usr/bin/setsid`, а PATH-подмена безопасно отвергается.
What changed: release проверяет root-владение и запрет group/world write для session launcher до gate и установки.
What changed: регрессия подменяет `setsid` через `PATH` и подтверждает реальную ошибку gate и отсутствие установки.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `bash -n ...`, `git diff --check` → PASS.
One next action: повторить Review доверенной цепочки gate.

## LOG

### 2026-08-12 — Implement

Session launcher закреплён как `/usr/bin/setsid`; перед gate проверяются root-владелец
и отсутствие записи для group/world. PATH-подмена больше не может сфабриковать
успех: регрессия получила настоящий отказ gate, не допустила сборку и установку;
целевой shell-набор прошёл.

### 2026-08-12 — Implement

После readiness PGID сохраняется только в памяти release, поэтому launcher больше не
может изменить будущую цель сигнала заменой handshake. Перед остановкой сверяется
лидер session и его принадлежность дереву launcher; регрессия подменяет PGID на
постороннюю группу и подтверждает, что она не получает TERM. Shell-набор, Go-тесты,
Go-сборка и production-сборка web прошли.

### 2026-08-12 — Implement

Реализация перебазирована на свежий `origin/main`; актуальная модель запуска служб
учтена в проверке однократной установки. Целевой shell-сценарий подтвердил, что
launcher не может подменить результат настоящего gate, а сборка Go и проверки
синтаксиса/диффа прошли.

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
