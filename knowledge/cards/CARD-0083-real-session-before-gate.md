# Реальная session регистрируется до запуска gate

## HEAD

Status: IMPLEMENTED: требуется независимая Verify полного сценария.
Branch: factory/679963e3-028-b412b1c3-498.
Implementation commit: bf5aa3c537047ee09d171d5335d5532e789db5b2 — cleanup gate не может завершить тестовый раннер или группу самого релиза.
What changed: shell-фикстура запускает release в отдельной session; `fx-factory-release` отказывается сигналить собственной process group.
What changed: изменения CARD-0083 перенесены поверх свежего `origin/main` с сохранением его release-механизма.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и `git diff --check` завершились успешно.
One next action: Verify запускает полный `bash ops/test-fx-factory-release.sh` в чистом worker и фиксирует результат.

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
