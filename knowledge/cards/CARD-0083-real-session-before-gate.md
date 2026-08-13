# Реальная session регистрируется до запуска gate

Implementation commit: 63a2faea86d02f85d08d3e7dd3dd469096300d8e — регрессия подтверждает ошибку настоящего gate за форкающим launcher даже при подделанном успехе.

## HEAD

Status: Implemented and target-tested — awaiting Verify.
Branch: factory/c2f38b47-944-d44d6f63-7ab.
Implementation commit: 63a2faea86d02f85d08d3e7dd3dd469096300d8e — регрессия подтверждает ошибку настоящего gate за форкающим launcher даже при подделанном успехе.
What changed: работа перенесена на свежий `origin/main`; дублирующий production patch не нужен, поскольку безопасная launcher-цепочка уже в main.
What changed: adversarial-сценарий пишет поддельный `status=0`, затем роняет настоящий forked Go gate и требует build error без установки и утечки процессов.
Evidence: `timeout 300 bash ops/test-fx-factory-release.sh` → PASS; `bash -n ops/test-fx-factory-release.sh ops/fx-factory-release` и `git diff --check` → PASS.
Evidence: `FACTORY_BUILD_DIR=<tmp> just build` → PASS, три бинарника; `just check` остановлен существующим `SA4000` в `internal/worker/attempt_lifecycle_test.go:31` вне области.
One next action: Verify выполняет один полный набор проекта и проверяет поставку ветки.

## LOG

### 2026-08-12 — Implement

После ответа владельца crash-cleanup запускается отдельно и каждый release, signal и driver-сценарий ограничен `/usr/bin/timeout`; recovery сбрасывает переменную crash hook.
Исправлены повторное использование `path-shadow-chain`, неполный trusted-gate env в runner-ах и устаревший anti-spoof fixture; небезопасный result path по-прежнему не передаётся.
Полный shell-suite завершился PASS для crash-фаз `prepared`, `old-stopped`, `pair-installed`, `services-started`, rollback, signal и PATH/anti-spoof проверок.

### 2026-08-13 — Implement

После ревью clone/checkout, определение commit и subject переведены с `as_user git`
на root-owned `/usr/bin/git`, поэтому подменённый PATH-Git не участвует до проверки
объекта. Возвращён fallback snapshot через свежесобранный server, когда установленный
server не знает новую схему; фикстура проверяет оба сценария. `bash -n` и `git diff --check`
прошли; полный shell-suite остановился на существующем crash-cleanup разделе.

### 2026-08-12 — Implement

Безопасный Gate перенесён поверх свежего `main`: исполняемый скрипт и полный набор
его зависимостей извлекаются по blob из конкретного Git-commit в закрытый root-owned
каталог. После разрешения конфликтов Node также закреплён абсолютным проверяемым путём.
`bash -n` и `bash ops/test-fx-factory-release.sh` прошли, включая конкурентную подмену
каталога, замену Gate и PATH-shadow для `setsid` и Node.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Gate-цепочка запускается только по доверенным путям | `bash ops/test-fx-factory-release.sh` | PASS: проверены trusted executable, PATH-shadow, Node/npm/npx, реальная session, handshake, параллельные gate, единая установка и общий откат. |
| Регрессии смежного релизного поведения | тот же shell-suite | PASS: регистрация, rollback, signal cleanup и отсутствие утечек процессов подтверждены. |
| Полный набор проекта | `just check` | НАХОДКА: форматирование, vet, govulncheck, staticcheck, boundary и Go-тесты PASS; UI lint не запустился в чистом окружении из-за отсутствующего `eslint` (`exit 127`). |
| Закреплённая область поставки | isolated bare fetch; `git diff --name-only base_sha...candidate_sha` | PASS: `knowledge/cards/CARD-0083-real-session-before-gate.md`, `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`; implementation commit `be58e8096302044be7e96ee96a9e32aef93ddd08` — предок кандидата и меняет код. |
| Чистота | `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`; `git diff --check` | PASS. |

Полный набор не стал причиной возврата: отказ относится к отсутствующей локальной
UI-зависимости, а целевой gate-suite прошёл полностью.

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

### 2026-08-12 — Implement

UI gate теперь передаёт проверенные `npm` и `npx` закреплённому абсолютному Node,
поэтому подложенный `PATH/node` больше не превращает невозможную команду в успех.
Вложенный release gate в фикстуре заменён bounded stub: целевой self-test завершился
с PASS за 150 секунд без рекурсивного роста процессов. Полный Verify зелёный до
неизменённого browser-контракта pause/resume; его отдельный повтор воспроизвёл дефект main.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Gate запускается только из доверенной неизменяемой цепочки | `timeout 300 bash ops/test-fx-factory-release.sh` | PASS: абсолютные Git/setsid/Node/npm/npx, nonce-handshake, real-session, PATH-shadow, spoof и конкурентная подмена Gate проверены. |
| Crash recovery ограничен по времени | тот же shell-suite, фазы `prepared`, `old-stopped`, `pair-installed`, `services-started` | PASS: все журналы восстановлены, suite завершился сам с кодом 0. |
| Регрессии release lifecycle | тот же shell-suite | PASS: регистрация, единая установка, rollback, HUP/TERM cleanup и отсутствие утечек процессов проверены. |
| Полный набор проекта | `just check` | НАХОДКА вне области: vet и govulncheck PASS; staticcheck остановился на существующем `internal/worker/attempt_lifecycle_test.go:31` (`SA4000`). |
| Закреплённая поставка | isolated bare fetch; `git diff --name-only e43462307fcd7c25003eecfe693fd21a9dfe8ba7...f56152de979f841d779ced73442f5f55241508b3` | PASS: изменены только карточка и два release-скрипта; implementation commit `f97fe77d83f844426623f2a0e8a2a27ffb3cc603` валиден. |
| Чистота | `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`; pinned `git diff --check` | PASS. |

### 2026-08-12 — Implement

После конфликта с актуальным `main` сохранена только отсутствовавшая регрессия:
фикстура подделывает успешный файловый result, но настоящий forked Go gate завершается
ошибкой. Release возвращает build error 5, не устанавливает бинарники и не оставляет
процессы. Целевой shell-suite, shell syntax и `git diff --check` завершились PASS.
Сборка трёх бинарников прошла; общий `just check` остановился на существующем
`SA4000` в `internal/worker/attempt_lifecycle_test.go:31`, который ветка не меняет.
