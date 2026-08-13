# Реальная session регистрируется до запуска gate

Implementation commit: d60b82f2a181bbb5c7d6e90c802f4422eedeef27 — gate принимает итог только из kernel wait защищённой launcher-цепочки.

## HEAD

Status: Implemented and tested — ready for review.
Branch: factory/f8bde6d7-cff-7d818d98-75a.
Implementation commit: d60b82f2a181bbb5c7d6e90c802f4422eedeef27 — gate принимает итог только из kernel wait защищённой launcher-цепочки.
Pinned base: e43462307fcd7c25003eecfe693fd21a9dfe8ba7 (`origin/main`).
Pinned implementation candidate: d60b82f2a181bbb5c7d6e90c802f4422eedeef27.
What changed: удалён подделываемый файловый result protocol; восстановлены root-owned waitable chain, проверенные абсолютные пути и nonce/ack handshake.
What changed: adversarial-тест подсовывает `status=0`, пока настоящий gate падает, и подтверждает запрет установки.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS, включая forged result, PATH shadow, forked `setsid`, signal cleanup и rollback.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`; `git diff --check` → PASS.
One next action: review pinned candidate and merge.

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

### 2026-08-12 — Implement

После возврата с review удалён недоверенный `*.session.result`: gate снова запускается
фиксированной root-owned цепочкой через проверенные абсолютные executables, а итог
приходит только из kernel `wait` за `setsid --fork --wait`. Новый adversarial-сценарий
заранее пишет правдоподобный `status=0`, затем роняет настоящий Go gate; release
возвращает build error 5, не устанавливает бинарники и не оставляет процессов.
Целевой shell-suite и синтаксическая проверка прошли; база закреплена на
`e43462307fcd7c25003eecfe693fd21a9dfe8ba7`, реализация — на
`d60b82f2a181bbb5c7d6e90c802f4422eedeef27`.
