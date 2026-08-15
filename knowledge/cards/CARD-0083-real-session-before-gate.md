# Реальная session регистрируется до запуска gate

## HEAD

Status: IMPLEMENTED — обе находки review исправлены, выпуск не выполнялся.
Branch: factory/0044f851-d6c-1fe77d92-f72.
Implementation commit: b283b55c125fb9eda2a414de693cf43bc931f0a9 — cgroup-helper доставляется атомарно, а Pilot suite снова блокирует установку через Gate.
What changed: штатный installer обновляет `fx`, release-driver и cgroup-helper одной транзакцией с общим откатом.
What changed: Pilot suite возвращён в обязательную Go-группу; отрицательный сценарий доказывает, что после его падения установка не начинается.
Evidence: `bash ops/test-install-factory-control.sh` и `bash ops/test-fx-factory-release.sh` → PASS.
Evidence: Go-фазы `just check`; затем `just ui-check test-tooling test-launcher`, Pilot (306 tests) и Go/UI builds → PASS.
One next action: повторно провести независимый Review; выпуск до PASS не выполнять.

## LOG

### 2026-08-14 — Implement

После REQUEST CHANGES cgroup-helper включён в ту же атомарную транзакцию, что `fx`
и release-driver; upgrade и отказ последнего шага подтверждают установку и полный
откат. Pilot suite снова обязателен до release-сценария, а `pilot-test-fail`
подтверждает отсутствие установки. Целевые shell/Pilot-наборы, полный project check
и production-сборки прошли после rebase на свежий `main`; выпуск не запускался.

### 2026-08-14 — Implement

Ветка перебазирована на свежий `main`; cgroup/PATH-защита и её adversarial shell-набор
повторно прошли. Фикстура release broker приведена к новому контракту Pilot drop-in,
поэтому проверка больше не обращается к системному `/etc`. TypeScript `tsconfig.app`
проверен без генерации файлов; `git diff --check` чист.

### 2026-08-12 — Verify

| Проверка | Команда | Наблюдение |
| --- | --- | --- |
| Безопасный PATH и абсолютные tools | `bash ops/test-fx-factory-release.sh` | PATH-shadow сценарий включён в набор; набор не завершился из-за следующей проверки. |
| cgroup cleanup потомков | `bash ops/test-fx-factory-release.sh` | FAIL: `successful gate orphan was not drained in bounded time`. |
| Синтаксис и чистота diff | `bash -n ops/fx-factory-release ops/factory-gate-cgroup ops/install-factory-gate-cgroup.sh`; `git diff --check` | PASS. |
| Полный backend-набор | `just format-check && just vet && just vuln && just boundary && just test ...` | `format-check`, `vet`, `vuln` прошли; `just test` упал на timeout `internal/worker` через 300 секунд. |

Вердикт: BLOCKED. Изменённая cgroup-очистка не выполняет заявленное bounded fail-closed условие для orphan-потомка; установка должна оставаться запрещённой до исправления.

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

### 2026-08-11 — Implement

Итоговая защита перенесена без промежуточных изменений на `main`
`60cba840f39a453862c1c0f87f261fd453b09688` отдельным implementation-коммитом.
Три shell-прогона, полный Go test/build, 157 UI-тестов, UI build, `bash -n`
и `git diff --check` прошли; scope относительно свежей базы ограничен этой карточкой
и двумя gate-скриптами. Pilot не включался.

### 2026-08-11 — Implement

Security correction перенесена на свежий `main` `36ce322e2b6685dd9a87f4d2c947f61538654ae1`:
gate читает root-owned замороженный checkout, не допускает caller-controlled `$AS`,
а UI использует абсолютные Node/npm/npx с очищенным PATH. Успешный gate с реальным
фоновым потомком ограниченно проходит TERM→KILL/reap и превращается в отказ без
установки. Расширенный shell-suite ×2, Go build, 157 UI tests/build и syntax/diff прошли;
полный Go test повторил существующий на `origin/main` отказ схемы поля CARD-0087.

### 2026-08-11 — Implement

Security correction перенесена на зелёный `main` `3183424f924d440b686908f219d0013b7ee8c504`.
Release устанавливает безопасный PATH до первого external command и валидирует абсолютные
tools для checkout, lock, ownership, gates, установки и cleanup. Root launcher сначала
останавливается, входит в отдельную cgroup v2 и только затем запускает `setsid`; escaped
session очищается bounded TERM→KILL, делает gate неуспешным и не допускает install.
Shell-suite ×3, полный Go test/build, 157 UI tests/build, syntax/diff прошли; Pilot не включён.
