# CARD-0083 — Реальная session регистрируется до запуска gate

## HEAD

Status: BLOCKED: реальный root bootstrap/probe/rollback не выполнен; worker UID 994 и `sudo` запрещён через `no new privileges`.
Branch: factory/f2dc0140-801-bb9f9af1-47e.
Implementation commit: 6248ea2ae1305a72b41d7a0e9736fedaded7a9ea — закреплённый SHA-256 синхронизирован с финальным cgroup helper до Gate.
What changed: bootstrap, installer и release используют один SHA-256 фактического helper; тест сверяет все три digest до root-only проверки.
What changed: bootstrap канонизирует direct-child source, проверяет root owner и mode всей цепочки/файлов и откатывает helper, installer и bootstrap при ошибке.
Evidence: статическая SHA-256 сверка и shell-регрессии helper/installer/release → PASS; non-root bootstrap → явный SKIP.
One next action: повторный Review должен подтвердить согласованность digest; затем на root-runner выполнить живой bootstrap/probe/rollback.

## LOG

### 2026-08-12 — Implement

Исправлены три закреплённых SHA-256 по окончательному содержимому
`factory-gate-cgroup`; прежнее значение не позволяло bootstrap и release принять
поставленный helper. Статическая сверка всех трёх значений перенесена до проверки
UID, поэтому работает и на непривилегированном worker. Целевые shell-проверки и
syntax прошли; root-сценарий ожидаемо выдал `SKIP` без прав администратора.

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

### 2026-08-12 — Implement

Повторный полный набор на свободном worker прошёл: `go test ./...`,
`go build ./...`, `cd web && npm test -- --run` и `cd web && npm run build`.
Хост использует cgroup v2 (`cgroup2fs`), но процесс работает от UID 994, а
`sudo -n id` требует пароль. Поэтому обязательный root-bootstrap в изолированный
каталог и реальный запуск helper не выполнялись; до них статус остаётся BLOCKED.

### 2026-08-12 — Implement

Добавлена узкая одноразовая команда fx factory cgroup-helper-bootstrap: она
принимает только доверенный bootstrap-каталог, атомарно ставит control-пару,
делает живой cgroup v2 probe, создаёт marker и восстанавливает прежние файлы
при любой ошибке. Release теперь не открывает Gate без этого marker.
Целевые shell-проверки и syntax прошли; worker не может выполнить root-only часть.

### 2026-08-12 — Implement

Реализация заново перенесена на свежий main без замены release lifecycle:
сохранены `status`, `rollback`, `restore-db`, generation manifest, journal и
восстановление после прерывания. Bootstrap теперь отвергает неканонический путь,
непосредственно не вложенный каталог, небезопасные owner/mode всей цепочки и
изменённый helper; установка откатывает все три control-файла при ошибке.
Release-регрессия подтвердила marker/hash до Gate, cgroup attach до первой команды
Gate и штатные crash/recovery/rollback сценарии. Root-проверка честно завершилась
`SKIP`; Go и 159 UI тестов, обе сборки и целевые shell-проверки прошли.
