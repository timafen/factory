# Реальная session регистрируется до запуска gate

## HEAD

Status: BLOCKED: verify cannot complete — обязательный shell-тест релиза не завершился.
Branch: factory/4d0cca7e-228-85d28caf-e8b.
Implementation commit: 55f2a61f85fc8565ac31efc7ebbad161319a87a1 — gate получает реальную SID/PGID session до запуска проверок.
What changed: `fx-factory-release` получает атомарный handshake из оболочки после `setsid` и запускает `$AS`/gate только после него.
What changed: HUP/INT/TERM ограниченно завершают подтверждённую группу TERM→KILL и дочищают launcher, если handshake так и не появился.
Evidence: две изолированные попытки `bash ops/test-fx-factory-release.sh` не завершились; первая работала почти 3 минуты, вторая — более минуты, после чего были остановлены только процессы проверки. Повторная проверка потребовала перебазирования на свежий main и получила конфликты в обоих изменённых production-файлах.
One next action: автору разрешить конфликты с main и устранить зависание shell-сценария, затем повторить Verify.

## LOG

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
