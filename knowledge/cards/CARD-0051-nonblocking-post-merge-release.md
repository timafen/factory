# CARD-0051 — Автовыпуск не останавливает управление конвейерами

## HEAD

- Status: Verified PASS — автовыпуск сохраняется, не блокирует цикл Pilot и
  повторяется после внешней блокировки.
- Branch: `factory/3ea10dee-e5d-6daabe49-3e0`.
- Head commit: `6490a10` (`Зафиксировать повтор выпуска после внешней блокировки`).
- What changed: при `rc=8` Pilot сохраняет на диск один отложенный повтор, даже
  если новый merge ещё не успел выставить очередь. Повтор запускается после 60 секунд.
- Evidence: `python3 -m unittest pilot.test_pilot` — 103/103 OK, включая 11/11
  `PostMergeDeployTest`; Go-пакеты и UI lint/typecheck прошли. `just check`
  останавливается только на двух прежних staticcheck-находках вне области задачи.
- One next action: оркестратор автоматически вносит PASS-ветку в `main` и запускает
  staging-выпуск.

## LOG

### 2026-08-10 — Implement

Синхронный post-merge выпуск заменён сохраняемой фоновой очередью на среду.
Один активный выпуск принимает один коалесцированный повтор, а файл статуса
даёт следующему циклу собрать код завершения и вывод даже после рестарта Пилота.
Добавлены проверки асинхронного запуска, рестарта, коалесцирования и журнала;
`python3 -m unittest pilot.test_pilot` — 101/101 OK.

### 2026-08-10 — Implement

Синхронный `run_shell` заменён на учтённый фоновый запуск: запрос и поколение
сначала сохраняются в `state.json`, на одну среду допускается один процесс, а
результат собирается последующим циклом. Новые merge во время выпуска дают один
дополнительный выпуск свежего состояния; `rc=8` откладывает повтор. После
рестарта незабранный `running` и старый `pending_factory_deploy` восстанавливаются.

Журнал получает человекочитаемые события `started` и `completed` с `rc` и
однострочным выводом до 200 символов. Команды остались строго привязаны к
репозиториям: Factory выпускает Factory, tarser-operations — свой staging.

Проверки: `PostMergeDeployTest` — 9/9 OK, включая заблокированный выпуск и
обработку следующей завершённой задачи; полный `pilot.test_pilot` — 101/101 OK;
`go test ./...`, сборка двух Go-бинарей, `py_compile` и `git diff --check` — OK.

### 2026-08-10 — Implement

Запуск выпуска теперь сначала резервируется атомарной записью в `state.json`,
и только затем Pilot вызывает фоновый процесс и сохраняет его PID. Ожидающий
коалесцированный повтор также пишется сразу. Тест останавливает Pilot на границе
после сохранения, заново читает состояние с диска и подтверждает автозапуск:
`PostMergeDeployTest` — 10/10 OK; `py_compile` и `git diff --check` — OK.

### 2026-08-10 — Implement

После завершения фонового выпуска с `rc=8` Pilot не удаляет запрос: он сразу
сохраняет на диск один отложенный повтор на 60 секунд. Проверка моделирует внешний
release-lock, подтверждает сохранение очереди без нового merge и её запуск после
освобождения блокировки; `PostMergeDeployTest` — 11/11 OK, `py_compile` и
`git diff --check` — OK.

### 2026-08-10 — Verify

| Критерий | Команда/проверка | Наблюдение |
| --- | --- | --- |
| Выпуск не блокирует цикл Pilot | `PostMergeDeployTest.test_release_is_started_in_background_and_saved_for_next_cycle` | Процесс запускается через `Popen`, PID и состояние записаны на диск. |
| Рестарт не теряет выпуск | `PostMergeDeployTest.test_restart_from_state_file_resumes_release_saved_before_process_start` | Очередь, сохранённая до `Popen`, восстановлена и запущена следующим циклом. |
| Внешняя блокировка не теряет запрос | `PostMergeDeployTest.test_external_release_lock_is_saved_then_retried_after_delay` | `rc=8` создаёт сохраняемую очередь; до 60 секунд запуска нет, на 60-й секунде повтор стартует. |
| Повторные merge не плодят выпуски | `PostMergeDeployTest.test_busy_factory_release_is_coalesced_for_retry` и `test_completed_release_starts_one_coalesced_successor` | Занятый выпуск получает один coalesced-повтор. |
| Соседние среды не перепутаны | `PostMergeDeployTest.test_trading_repository_releases_only_trading_staging` и `test_factory_repository_uses_its_own_release_command` | tarser-operations выпускает staging, Factory — только свою команду. |

Полный Python-набор: `python3 -m unittest pilot.test_pilot` — 103/103 OK. Go:
`go test -timeout 5m` для всех 13 пакетов — OK. UI: после `just ui-install`
`npm run lint` и `npm run typecheck` — OK. `just check` воспроизводимо красный
только на staticcheck в `internal/controlplane/cards_http.go:37` и
`internal/controlplane/pilot_config.go:136`, обе строки существовали до ветки.
