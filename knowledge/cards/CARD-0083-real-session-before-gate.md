# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/f018da1b-c4b-2b08a042-172.
Implementation commit: 3f28de1058b2caee40b9452af4fe7bc9f8af2738 — релиз получает точный итоговый статус gate за форкающим launcher.
What changed: session-wrapper атомарно публикует running/final state настоящей команды, а supervisor принимает успех только из её `status=0`.
What changed: отсутствующий, повреждённый или осиротевший результат ограниченно завершается fail-closed; SID/PGID readiness и TERM→KILL сохранены.
Evidence: `bash ops/test-fx-factory-release.sh` ×3 → PASS; `go test -timeout 5m ./...`, `go build ./...`, `cd web && npm run build` → PASS.
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
