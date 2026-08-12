# Реальная session регистрируется до запуска gate

Implementation commit: 9c5dc01aed55dcb758bd0fb47c785c8c5ef01e0e — gate запускается только по проверенным абсолютным путям.

## HEAD

Status: BLOCKED — UI gate всё ещё допускает подмену `PATH/node`, а целевая фикстура рекурсивно запускает сама себя.
Branch: factory/69d506bf-bc3-68d5fa71-963.
Implementation commit: 9c5dc01aed55dcb758bd0fb47c785c8c5ef01e0e — gate запускается только по проверенным абсолютным путям.
Evidence summary: pinned comparison `9123aa42b01a39ce7f1fa998568189ab6d38b07b...1da13ab6cb6eb0056401a78df7dbf7e42f26d07e`; обычные UI/Go/build/security проверки зелёные, но `/usr/bin/npx` и `/usr/bin/npm` принимают подложенный `PATH/node` и возвращают ложный успех, а `bash ops/test-fx-factory-release.sh` уходит в рекурсивный self-test.
One next action: закрепить доверенный Node/runtime для UI gate и восстановить bounded-перехват вложенного release self-test, затем повторить Verify.

## LOG

### 2026-08-12 — Implement

Опубликована кандидатская ветка на свежем `main`; gate использует только проверенные
абсолютные пути, а PATH-shadow и поддельная session не допускаются. `bash
ops/test-fx-factory-release.sh`, `bash -n` и `git diff --check` прошли.

### 2026-08-12 — Implement

Перенесена на свежий `main` доверенная gate-цепочка: фиксированные абсолютные
executables, проверка владельца и прав, живая session с nonce/ack и kernel wait
status. Изолированная shell-фикстура подменяет `PATH`-`setsid` и подтверждает,
что он не участвует в запуске gate; `bash -n` и `git diff --check` также прошли.

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

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
|---|---|---|
| Сравнение с актуальной удалённой базой | `git ls-remote --symref origin HEAD`; изолированный fetch; сравнение только закреплённых SHA | base `9123aa42b01a39ce7f1fa998568189ab6d38b07b`, candidate `1da13ab6cb6eb0056401a78df7dbf7e42f26d07e`; непустой diff из трёх ожидаемых файлов |
| Вся UI gate-цепочка использует доверенные executables | `PATH=<node -> /bin/true> /usr/bin/npx definitely-not-a-real-command` и аналогично для `/usr/bin/npm` | BLOCKED: обе невозможные команды вернули `0`, потому что root-owned launchers используют `#!/usr/bin/env node` |
| Целевая release-фикстура ограниченно завершается | `bash ops/test-fx-factory-release.sh` | BLOCKED: фиксированный `/bin/bash` обошёл fixture-перехват и рекурсивно запустил self-test; за 65 секунд дерево выросло до 366 процессов, после `TERM` cleanup оставил 0 |
| Смежные UI/Go/release проверки | `just ui-check`, `just ui-build 0`, `just test-tooling`, `just build`, `just test-release`, `just test-launcher`, `just vet`, `just vuln`, `just staticcheck`, `just boundary`, `just test`, `just test-worker-race` | PASS: 158 UI-тестов, все Go-пакеты и race-сценарии зелёные; release-артефакты воспроизводимы; embedded UI не изменился |
| Синтаксис и чистота diff | `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`; `git diff --check 9123aa4...1da13ab` | PASS |
