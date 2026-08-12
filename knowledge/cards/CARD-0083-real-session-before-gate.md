# CARD-0083 — Реальная session регистрируется до запуска gate

## HEAD

Status: Implemented — awaiting human merge.
Branch: factory/bdeb3b62-b1e-fc42a2f1-976.
Implementation commit: dfca14a26f0665c726f452fd685cb644a5909118 — cgroup helper ограничен собственным корнем, а bootstrap ставит проверенный helper до gate.
What changed: helper отвергает `.`, `..`, separators и traversal; после канонизации допускает только путь строго ниже root-owned `CGROUP_ROOT`.
What changed: trusted control bootstrap ставит helper и installer от root с mode `0755` и SHA-256; release не выполняет candidate installer и fail-closed проверяет owner/mode/hash до gate.
Preserved: safe PATH, cgroup cleanup для escaped `setsid`, обязательные gates и выключенный Pilot.
Evidence: `bash ops/test-factory-gate-cgroup.sh`, `bash ops/test-install-factory-control.sh`, `bash ops/test-fx-factory-release.sh` → PASS.
Evidence: `go test ./...`, `go build ./...`, `cd web && npm test -- --run`, `npm run build`, `bash -n`, `git diff --check` → PASS (123 UI tests).
One next action: merge, then выполнить root bootstrap из доверенной поставки до первого factory release.

## LOG

### 2026-08-11 — Implement

Security correction after strict review: cgroup helper больше не может получить
родительский или чужой путь через имя группы; отдельная регрессия доказывает, что
`..` не открывает и не меняет parent `cgroup.kill`. Чистый bootstrap ставит
root-owned helper и control installer, проверяет mode/SHA-256, а release использует
только установленный installer и останавливается до candidate gate при missing или
altered helper. Shell hostile/installer fixtures, Go/UI build and tests, syntax и
`git diff --check` прошли; Pilot не включался.
