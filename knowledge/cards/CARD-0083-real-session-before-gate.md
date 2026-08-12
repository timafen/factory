# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting review.
Branch: factory/39c5a5e6-58c-22fb2ec9-cd7.
Implementation commit: dd356e644091977a0614fe8a36a7823e8e5193c9 — релиз получает точный итоговый статус gate за форкающим launcher.
What changed: session-wrapper атомарно публикует running/final state настоящей команды, а supervisor принимает успех только из её `status=0`.
What changed: отсутствующий, повреждённый или осиротевший результат ограниченно завершается fail-closed; SID/PGID readiness и TERM→KILL сохранены.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS.
One next action: повторная проверка переноса на свежий main.

## LOG

### 2026-08-12 — Implement

Перенесён session-supervisor на свежий main: он ждёт атомарно опубликованный
итоговый статус настоящей команды за форкающим launcher и закрывает ворота при
отсутствующем или повреждённом результате. Целевой shell-suite подтвердил
readiness, передачу статуса и TERM→KILL cleanup.

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
