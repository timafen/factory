# Реальная session регистрируется до запуска gate

## HEAD

Status: IMPLEMENTED: полный Verify пройден.
Branch: factory/e4258c26-c0d-c2b5d27e-3d2.
Implementation commit: a12ceded7e78b18ee1968afb2ea1d92704ca2b5c — cleanup gate не может завершить тестовый раннер или группу самого релиза.
What changed: shell-фикстура запускает release в отдельной session; `fx-factory-release` отказывается сигналить собственной process group.
What changed: реальная SID/PGID подтверждается до UI и Go gate, а сигнал завершает только подтверждённую группу.
Evidence: `bash ops/test-fx-factory-release.sh`, `bash -n` и `git diff --check` завершились успешно.
One next action: передать ветку на review.

## LOG

### 2026-08-12 — Implement

Перенесены только файлы CARD-0083 на свежий main и разрешены конфликты с текущим
release-механизмом. Фикстура isolирует session релиза, а cleanup отказывается
посылать групповой сигнал в собственную process group. `bash -n` и
`git diff --check` успешны; полный shell-тест требует независимого чистого worker.

### 2026-08-11 — Implement

Реальный wrapper после `setsid` записывает SID, PGID и ready атомарной заменой файла,
до запуска `$AS` и UI/Go gate. Shell-фикстуры принудительно форкают GNU `setsid` и
посредник `$AS`, отправляют HUP/INT/TERM до и после readiness, оставляют дочерние
процессы игнорировать TERM и подтверждают bounded cleanup, отсутствие процессов и
отсутствие production install. Полный shell-тест, Go test/build и UI production build прошли.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Реальная SID/PGID зафиксирована до gate | просмотр `07491cc7b26bbc47dca9f8fd5109f2c665f1fa53...af3c02a9f655a1fa61107d46b6680f47a3bdb15c` | wrapper после `setsid` атомарно записывает `sid`, `pgid`, `ready=1` до `$AS` и команды. |
| Gate не стартует без handshake | `bash ops/test-fx-factory-release.sh` | BLOCKED: тест не завершился в двух независимых запусках; результат нельзя засчитать. |
| HUP/INT/TERM не оставляют forked gate | сценарии `signal-forked-gates` и `signal-before-ready` в shell-тесте | сценарии присутствуют, но общий обязательный тест не завершился, живое подтверждение отсутствует. |
| Ветка готова к слиянию с актуальным main | `git fetch origin main && git rebase origin/main` | BLOCKED: конфликты в `ops/fx-factory-release` и `ops/test-fx-factory-release`; rebase отменён без изменения кода. |

Проверка дерева: изменений вне карточки нет; `git diff --check` по кандидату не вывел ошибок пробелов.

### 2026-08-12 — Implement

Полный `bash ops/test-fx-factory-release.sh` повторно запущен на чистом
Verify-worker и завершился успешно: handshake реальной session предшествует gate,
а сценарии HUP/INT/TERM дочищают forked процессы. `bash -n` и
`git diff --check` по `9123aa42b01a39ce7f1fa998568189ab6d38b07b...HEAD` также успешны.
