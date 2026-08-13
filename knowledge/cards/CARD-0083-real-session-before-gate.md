# Реальная session регистрируется до запуска gate

Implementation commit: 15ec2bc41c3e02550e74278786932fe95c9df109 — регрессионная проверка закрепляет автоматическое слияние после успешной Verify.

## HEAD

Status: Verified PASS — автоматически передаётся в main и staging.
Branch: factory/500d1efb-715-3f528c50-683.
Implementation commit: 15ec2bc41c3e02550e74278786932fe95c9df109 — регрессионная проверка закрепляет автоматическое слияние после успешной Verify.
What changed: проверка Gate за форкающим launcher уже включена в `main` коммитом `f2d9cce8f9038c566e3f2caf6df925d6d3c1bba2`.
What changed: регрессионный тест запрещает Verify снова сообщать владельцу об ожидании ручного merge.
Evidence: `python3 -m unittest pilot.test_pilot.VerifyDecisionGuideTests -v` → PASS; `just check` остановился только на известном `SA4000` в `internal/worker/attempt_lifecycle_test.go:31` вне области поставки.
One next action: оркестратору автоматически передать успешно проверенную ветку в main и staging.

## LOG

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Verify не ждёт ручного merge | `python3 -m unittest pilot.test_pilot.VerifyDecisionGuideTests -v` | PASS: тест фиксирует автоматическое squash-слияние в `main`, deploy в staging и ручное решение только для production. |
| Подсказка соответствует контракту | `grep` в `pilot/pilot.py` | PASS: текст направляет успешную Verify в `main` и staging автоматически. |
| Полный набор проекта | `FACTORY_DATA_HOME=$(mktemp -d) just check` | НАХОДКА вне области: после PASS `go vet` и `govulncheck` остановлен `SA4000` в `internal/worker/attempt_lifecycle_test.go:31`. |
| Чистота поставки | `git diff --check <base>...<candidate>` | PASS: ошибок пробелов нет; затронуты только карточка и целевой тест. |

### 2026-08-13 — Implement

HEAD приведён к фактическому состоянию: проверка Gate уже включена в `main`, поэтому
ручное слияние не ожидается. Добавлен регрессионный тест подсказки Verify: успешная
автоматическая проверка передаёт ветку в `main` и staging, решение владельца остаётся
только для production. Целевая Python-проверка и проверка пробелов прошли.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Launcher ждёт оба forked Gate | `timeout 300 bash ops/test-fx-factory-release.sh` | PASS: fixture видит `--fork --wait` дважды. |
| Ошибка Gate не теряется | тот же suite, `forked-gate-fail` | PASS: release возвращает code 5 и сохраняет Gate status 1. |
| После отказа нет build/install | тот же suite | PASS: старые binaries целы, events пуст, `go build` не вызвался. |
| Смежный release lifecycle | тот же suite | PASS: Gate, единая установка, регистрация, rollback и cleanup. |
| Полный набор проекта | `just check` | НАХОДКА вне области: `internal/worker/attempt_lifecycle_test.go:31` (`SA4000`); vet и govulncheck PASS. |
| Синтаксис и чистота | `bash -n ...`; `git diff --check` | PASS. |

Pinned review: base `5d9f3f330412bc59ab9b689d1ca3315ea137c0b3`, candidate `517fc3dd33f9fe4c2457df68cf1d8c9a3acd6790`;
после rebase кодовый implementation commit — `d320c99f3948000fb7c11d21e749337a279d3e1d`.

### 2026-08-12 — Implement

После конфликтов с main проверка форкающего launcher дополнена явным контрактом
`--fork --wait`: релиз ждёт kernel exit status обеих Gate-групп, а не ранний успех
родительского launcher. Shell-suite подтвердил отказ с code 5 без установки и сборки.

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

Регрессия подделывает успешный result рядом с настоящим forked gate и требует вернуть
исходную ошибку 5 без сборки и установки. Изолированный сценарий с внешним timeout,
внутренним timeout и trap-очисткой завершился PASS с кодом 0; синтаксис и diff-check прошли.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Ошибка настоящего forked gate не теряется за launcher | `timeout 180s env FACTORY_TEST_ONLY=forged-gate-result FACTORY_RELEASE_TEST_TIMEOUT=60 bash ops/test-fx-factory-release.sh` | PASS: реальная ошибка gate победила поддельный успех, установка не запускалась, exit 0 у self-test. |
| Смежное release-поведение | `bash -n` для обоих скриптов; pinned `git diff --check` | PASS: синтаксис и пробелы корректны. |
| Полный набор проекта | `timeout 1200s just check` | НАХОДКА вне области: format, vet и govulncheck PASS; staticcheck остановился на существующем `internal/worker/attempt_lifecycle_test.go:31` (`SA4000`). |
| Закреплённая область поставки | isolated bare fetch; `git diff --name-only c28b5bfc0c5bbb22c7d69d0749c316a2b340841e...2be97a66737caee20ee1a7390d1ba68f38a9f606` | PASS: изменены только карточка и `ops/test-fx-factory-release.sh`; implementation commit `13c8e8e0a04854c17c352eb8128eb85bb16fd04d` — предок кандидата и меняет код. |
