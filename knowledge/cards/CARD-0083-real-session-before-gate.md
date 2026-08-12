# CARD-0083 — Реальная session регистрируется до запуска gate

## HEAD

Status: BLOCKED: требуется root-runner для обязательной живой проверки helper и bootstrap.
Branch: factory/bdeb3b62-b1e-fc42a2f1-976.
Implementation commit: 2b5c1d9a43e2a49029f45f2fff425a4de83a3a30 — cgroup helper ограничен собственным корнем, а bootstrap ставит проверенный helper до gate.
What changed: helper отвергает `.`, `..`, separators и traversal; после канонизации допускает только путь строго ниже root-owned `CGROUP_ROOT`.
What changed: trusted control bootstrap ставит helper и installer от root с mode `0755` и SHA-256; release не выполняет candidate installer и fail-closed проверяет owner/mode/hash до gate.
Preserved: safe PATH, cgroup cleanup для escaped `setsid`, обязательные gates и выключенный Pilot.
Evidence: `bash ops/test-factory-gate-cgroup.sh`, `bash ops/test-install-factory-control.sh`, `bash ops/test-fx-factory-release.sh` → PASS.
Evidence: живой `stat -fc %T /sys/fs/cgroup` → `cgroup2fs`; worker UID 994, поэтому helper остановился на обязательной проверке `root is required` до действия. Полные Go/UI проверки не дали доказательства: Go toolchain/cache не собрал стандартную библиотеку, а UI-набор получил два несвязанных timeout при нагрузке.
One next action: на root-runner выполнить bootstrap в изолированный каталог и запуск helper на cgroup v2, затем повторить полный Go/UI набор в исправной среде.

## LOG

### 2026-08-11 — Implement

Security correction after strict review: cgroup helper больше не может получить
родительский или чужой путь через имя группы; отдельная регрессия доказывает, что
`..` не открывает и не меняет parent `cgroup.kill`. Чистый bootstrap ставит
root-owned helper и control installer, проверяет mode/SHA-256, а release использует
только установленный installer и останавливается до candidate gate при missing или
altered helper. Shell hostile/installer fixtures, Go/UI build and tests, syntax и
`git diff --check` прошли; Pilot не включался.

### 2026-08-11 — Verify

| Критерий | Команда/проверка | Наблюдение |
| --- | --- | --- |
| Небезопасное имя cgroup не может достичь родителя | `bash ops/test-factory-gate-cgroup.sh` | PASS: `.`, `..`, traversal, `/` и `\\` отвергнуты до записи `cgroup.kill`. |
| Bootstrap ставит согласованную защищённую пару control tools | `bash ops/test-install-factory-control.sh` | PASS: невалидные источники отвергнуты, установленная пара сохранена. |
| Release проверяет helper до candidate gate | `bash ops/test-fx-factory-release.sh` | PASS: hostile и missing/altered-helper fixtures прошли. |
| Реальная среда использует cgroup v2 | `stat -fc %T /sys/fs/cgroup` | PASS: `cgroup2fs`; реальный helper не запущен, так как worker UID 994 не root. |
| Полный Go-набор и сборка | `go test ./...`, `go build ./...` | BLOCKED: локальная Go 1.25.12 toolchain/cache сообщает отсутствующие stdlib packages до тестов проекта. |
| Полный UI-набор и build | `cd web && npm ci && npm test -- --run && npm run build` | BLOCKED: два timeout по 5 s в несвязанных `Projects`/`Dialog`; общий UI build конкурировал с процессами других worktree. |

Вердикт: BLOCKED — требуемое root-доказательство bootstrap/helper и полный чистый набор не получены; кодовые shell-регрессии прошли.
