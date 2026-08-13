# Реальная session регистрируется до запуска gate

Implementation commit: e936207df35cb3c44b254bb684309b801a463159 — release сохраняет точный итог forked gate.

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: factory/563a82cf-7c2-19d70f5e-5ad.
Implementation commit: e936207df35cb3c44b254bb684309b801a463159 — release сохраняет точный итог forked gate.
What changed: supervisor ждёт authoritative status настоящей команды за форкающим launcher.
What changed: пропавший или повреждённый результат завершается fail-closed, без установки.
Evidence: pinned remote comparison `base_sha=2cacc50ec06bacb069c53179f1cdb96871aed84b`, `candidate_sha=e506f64408fa343cf42dbd9d21a9c944e3171f64` → PASS; changed files are exactly the launcher, its test, and this card.
Evidence: adversarial shell suite, syntax check, `just test-launcher`, `just test-worker-race`, `just build`, and `just test-release` → PASS after rebase onto fresh `origin/main`.
One next action: human merge after reviewing the corrected pinned evidence.

## LOG

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

### 2026-08-12 — Implement

Исправлены устаревшие координаты поставки: pinned comparison повторён между
`2cacc50ec06bacb069c53179f1cdb96871aed84b` и
`e506f64408fa343cf42dbd9d21a9c944e3171f64` в изолированном bare-репозитории.
Сравнение подтвердило ровно launcher, его тест и карточку; целевые проверки и сборка PASS.
