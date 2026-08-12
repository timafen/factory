# Реальная session регистрируется до запуска gate

## HEAD

Status: IMPLEMENTED: блокирующее замечание review исправлено, проверки зелёные.
Branch: factory/068641a8-6d1-ffd09b88-a69.
Implementation commit: 7b0bb7640d523799327ce2171b3c580f8a6a2df3 — handshake с PGID релиза отклоняется до запуска gate, launcher и потомки очищаются TERM→KILL.
What changed: wrapper сверяет реальный PGID с группой релиза до публикации readiness и `exec` gate.
What changed: регрессионная фикстура подменяет SID/PGID на release PGID и подтверждает bounded cleanup без запуска gate и утечек процессов.
Evidence: release shell suite — PASS; Go test/build — PASS; UI 158 tests/build/lint — PASS.
One next action: повторить Review ветки.

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

### 2026-08-12 — Implement

Handshake с SID/PGID, совпадающими с process group релиза, теперь отклоняется
в wrapper до readiness и `exec` gate. Ошибочный launcher и уже созданные им
потомки завершаются ограниченным TERM→KILL без сигнала группе самого релиза.
Регрессионный release-сценарий, Go test/build, UI 158 tests/build/lint,
`bash -n` и `git diff --check` завершились успешно.
