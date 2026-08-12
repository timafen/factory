# Реальная session регистрируется до запуска gate

Implementation commit: 7a3cad982966e3ff689f473add6a7222eb5d5db7 — gate запускается только по проверенным абсолютным путям.

## HEAD

Status: Implemented — ready for review.
Branch: factory/69d506bf-bc3-68d5fa71-963.
Implementation commit: 7a3cad982966e3ff689f473add6a7222eb5d5db7 — gate запускается только по проверенным абсолютным путям.
What changed: `setsid`, оболочка, UI/Go-команды и gate-script закреплены за абсолютными root-owned путями; `$AS` исключён из цепочки результата.
What changed: nonce-handshake принимается только от живого session leader, а результатом gate остаётся kernel wait status доверенного launcher.
Evidence: `bash ops/test-fx-factory-release.sh`, `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`, `git diff --check` → PASS; fixture с подменённым `PATH`-`setsid` не входит в gate-цепочку.
One next action: rerun Review against this published branch.

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
