# CARD-0083 — Реальная session регистрируется до запуска gate

## HEAD

Status: READY FOR REVIEW: чистый host bootstrap выполним, а cgroup удаляется только после остановки всех Gate-процессов.
Branch: factory/b795a128-396-e4ee8365-bfc.
Implementation commit: c1e976a6f0e85b2355962094774caf632ff6bd19 — добавлены полный root-bootstrap, TERM/KILL cleanup и проверка атомарного отката.
What changed: `ops/README.md` даёт точные root-команды создания защищённого `/run/factory-release-gate/bootstrap-*`, live probe и проверки marker.
What changed: cleanup ограниченно ждёт после TERM, затем посылает KILL через helper, повторно проверяет пустоту cgroup и только потом удаляет её.
Evidence: shell release/bootstrap/helper/installer tests → PASS (root live probe → SKIP без root); Go tests/build и 160 UI tests/build → PASS.
One next action: выполнить root-процедуру из `ops/README.md` на новом cgroup v2-хосте и проверить созданный marker.

## LOG

### 2026-08-12 — Implement

Закрыты замечания повторного review: инструкция теперь содержит выполнимую с
нуля подготовку защищённого source-каталога и проверку marker; cleanup после
TERM ограниченно ждёт, добивает отделившийся TERM-устойчивый процесс через
cgroup helper, повторно проверяет пустоту и лишь затем удаляет группу. Возвращён
failpoint-тест отката между заменами installer. Release, helper и installer
shell-тесты, Go tests/build и 160 UI tests/build прошли; root live probe на
непривилегированном worker ожидаемо завершился SKIP.

### 2026-08-12 — Implement

После перебазировки на свежий `main` cgroup attach перенесён внутрь trusted
handshake до ack, поэтому команда Gate не стартует до помещения в cgroup.
Fixture передаёт helper всем launchers и проверяет его удаление после Gate.
`bash ops/test-fx-factory-release.sh`, installer, helper и bootstrap shell-тесты
прошли; root-only живой probe на worker недоступен и остаётся следующим действием.

### 2026-08-12 — Implement

Замкнутый путь первой установки заменён документированной ручной процедурой:
root клонирует репозиторий, сверяет commit `origin/main` и запускает
`install-factory-control.sh` с bootstrap-флагом, не вызывая `fx`. Root-ветка
регрессии теперь использует защищённый `/run` fixture, начинается без helper и
проверяет успешную установку при `fx`, который завершился бы ошибкой при запуске.
`bash -n` и `bash ops/test-install-factory-control.sh` прошли; живой marker всё
ещё требует отдельного запуска root на целевом cgroup v2-хосте.

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
