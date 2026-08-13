# Реальная session регистрируется до запуска gate

Implementation commit: f97fe77d83f844426623f2a0e8a2a27ffb3cc603 — crash-cleanup и все release-проверки Gate завершаются bounded и зелёно.

## HEAD

Status: Verified — реализация и целевые испытания завершены.
Branch: factory/f851f8f5-7e7-0715f029-f5f.
Implementation commit: f97fe77d83f844426623f2a0e8a2a27ffb3cc603 — crash-cleanup и все release-проверки Gate завершаются bounded и зелёно.
What changed: crash recovery очищает hook перед повторным запуском; каждый release, signal и driver-сценарий имеет жёсткий timeout.
What changed: разделены повторные PATH-fixture, добавлены trusted-gate env для фоновых и rollback runner; anti-spoof контракт сохранён.
Evidence: полный `bash ops/test-fx-factory-release.sh` → PASS; `bash -n`, `git diff --check`, `go test ./...`, `go build ./cmd/factory-release-broker` → PASS.
One next action: передать rebased branch на слияние.

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
