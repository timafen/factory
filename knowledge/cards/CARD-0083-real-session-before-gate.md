# Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/4d0cca7e-228-85d28caf-e8b.
Implementation commit: 55f2a61f85fc8565ac31efc7ebbad161319a87a1 — gate получает реальную SID/PGID session до запуска проверок.
What changed: `fx-factory-release` получает атомарный handshake из оболочки после `setsid` и запускает `$AS`/gate только после него.
What changed: HUP/INT/TERM ограниченно завершают подтверждённую группу TERM→KILL и дочищают launcher, если handshake так и не появился.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `go test -timeout 5m ./...`, `go build ./...` и `cd web && npm run build` → PASS.
One next action: human merge into main.

## LOG

### 2026-08-11 — Implement

Реальный wrapper после `setsid` записывает SID, PGID и ready атомарной заменой файла,
до запуска `$AS` и UI/Go gate. Shell-фикстуры принудительно форкают GNU `setsid` и
посредник `$AS`, отправляют HUP/INT/TERM до и после readiness, оставляют дочерние
процессы игнорировать TERM и подтверждают bounded cleanup, отсутствие процессов и
отсутствие production install. Полный shell-тест, Go test/build и UI production build прошли.
