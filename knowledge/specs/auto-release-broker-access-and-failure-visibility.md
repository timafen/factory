# Спецификация: восстановить автопоезд выпуска и честно показать его отказ

## Цель и влияние на владельца

Автоматический выпуск Factory должен снова проходить всю цепочку: Pilot после
слияния подключается к привилегированному broker, broker запускает только
разрешённый root-owned release driver без `sudo`, а Pilot завершает ожидающие
работы только после доказанного успешного выпуска. Если выпуск не прошёл,
владелец получает одну понятную запись в журнале и одно уведомление, а на
Обзоре видит неуспешный текущий или последний состав без технических SHA, PID
и внутренних идентификаторов.

Отдельная цель — безопасно разобрать уже возникший инцидент с 28 осиротевшими
ожиданиями. Их нельзя закрывать по возрасту, общей фазе поколения или факту
ручного запуска. Каждое ожидание закрывается только по явному списку и только
если проверенный merge-коммит действительно вошёл в установленный и успешно
завершённый ручной выпуск. Эта поставка готовит проверяемый механизм и
операционный манифест; применение к живому state не входит в автоматический
deploy и требует отдельного подтверждения оператора.

## Технический подход и реальные файлы

### Доступ Pilot к Unix-сокету

Фактический consumer `/run/factory/project-release-broker.sock` находится в
`pilot/pilot.py`, однако `ops/install-project-release-broker.sh` сейчас создаёт
`SupplementaryGroups=factory-release` для `factory-server.service`. Нужно
перенести drop-in на
`/etc/systemd/system/factory-pilot.service.d/50-project-release-broker.conf`,
переименовать связанный env override с `...SERVER_DROPIN` на
`FACTORY_RELEASE_BROKER_PILOT_DROPIN` и после `daemon-reload` перезапускать
`factory-pilot.service`, чтобы новая supplementary group попала в реальный
процесс. Broker устанавливается/перезапускается до Pilot.

`ops/fx-factory-release` должен собирать этот Pilot drop-in в generation
inventory и bootstrap/rollback snapshot под тем же фиксированным target. При
upgrade installer удаляет прежний ошибочный server drop-in только после
успешной атомарной установки Pilot drop-in; fixture проверяет отсутствие
нового server drop-in, наличие Pilot drop-in и restart Pilot. Удаление legacy
файла не должно оставлять систему без рабочего Pilot drop-in при ошибке.

Реальные файлы: `ops/install-project-release-broker.sh`,
`ops/test-install-project-release-broker.sh`, `ops/fx-factory-release`,
`ops/test-fx-factory-release.sh`.

### Passwordless fixed-path запуск Factory adapter

`internal/releasebroker/broker.go` сейчас отображает все adapters в аргументы
общего `/usr/local/bin/fx`. У `ops/fx` non-root ветка сама вызывает `sudo`, что
несовместимо с `NoNewPrivileges=true` посредника и вообще не нужно для уже
привилегированного broker. Для двух Factory adapters executor выбирает
напрямую фиксированный root-owned `/usr/local/lib/fx-factory-release`:

| Adapter | Executable и argv |
| --- | --- |
| `fx-factory-release` | `/usr/local/lib/fx-factory-release <commit_sha>` |
| `fx-factory-rollback` | `/usr/local/lib/fx-factory-release --rollback` |

Остальные adapters сохраняют существующий `/usr/local/bin/fx` и текущий argv;
их протокол и поведение не меняются. Выбор executable и argv остаётся
code-owned allowlist: абсолютный путь не приходит из POST, shell не
используется, PATH не участвует в выборе программы. Test seam разделяется на
`factory release executable` и общий `fx executable`, чтобы интеграционный
тест доказывал именно выбранный бинарник. Статусы exit code `8` и `6` остаются
без изменений.

Реальные файлы: `internal/releasebroker/broker.go`,
`internal/releasebroker/broker_test.go`,
`cmd/factory-release-broker/main.go`, `pilot/test_pilot.py`.

### Дедуплицированный terminal failure и Overview

Успешный путь уже создаёт receipt и outbox `<generation_id>:done`, а ветка
terminal failure в `poll_delivery_state()` только сохраняет `phase=failed`.
Нужно добавить отдельный failure event с детерминированным ключом
`<generation_id>:failed`. Он сначала сохраняется в durable state, затем
`dispatch_delivery_outbox()` append-once пишет локальную journal-запись и
вызывает `notify()` с тем же `journal_id`. Повторный poll/restart не создаёт
вторую локальную запись или второе логическое уведомление. Транспорт push
остаётся best-effort/at-least-once, а локальная история дедуплицируется.

Failure event содержит только безопасные данные: target, человекочитаемые
названия waits, terminal category и время. В owner-facing тексте нет SHA,
PID, operation/generation/task id и сырого stdout. Переход остаётся `failed`:
`_complete_generation()`, delivery receipts и `mark_final(..., true)` не
вызываются, waits не закрываются. Один failure event относится ко всему
составу, а не создаётся по событию на каждого пассажира.

`release_train_block()` обязан показывать текущий `failed` и последний
terminal `failed` после появления следующего состава. Сейчас проекция уже
скрывает технические поля; изменение закрепляет правило выбора `previous`,
чтобы текущий terminal состав не дублировался как «прошлый», а после N+1
последний N был виден как ошибка. `web/src/Overview.tsx` показывает
человеческий текст «выпуск не прошёл»/«прошлый состав: ошибка» и список работ,
не раскрывая внутренние поля.

Реальные файлы: `pilot/pilot.py`, `pilot/test_pilot.py`,
`web/src/Overview.tsx`, `web/src/Overview.test.ts`.

### Адресная сверка ровно 28 осиротевших waits

Добавить one-shot инструмент `ops/reconcile-factory-delivery-waits.py` и
fixture `ops/test-reconcile-factory-delivery-waits.py`. Инструмент по умолчанию
ничего не меняет и не принимает путь live state неявно. На вход передаются:

- read-only копия `pilot/state.json` и её ожидаемый SHA-256 preimage;
- `factory-current.json`, manifest текущего generation и отсутствие
  незавершённого release transaction journal;
- свежий checkout/fetch репозитория для ancestry-проверки;
- reviewable JSON-манифест с target `factory`, SHA ручного выпуска и ровно 28
  уникальными парами `task_id + verified_merge_sha`.

Инструмент требует одновременного выполнения всех условий:

1. SHA в `factory-current.json`, `manifest.candidate_sha` и манифесте сверки
   одинаков; metadata опубликованы только после health, регистрации воркера и
   committed release в существующем driver.
2. Незавершённого release transaction journal нет, а current generation
   указывает на проверенный manifest.
3. Набор из 28 `task_id` точно равен набору waits выбранного осиротевшего
   поколения: без пропущенных, дополнительных, повторных или уже завершённых
   записей.
4. Для каждого `task_id` сохранённый `merge_intent.commit_sha` совпадает с
   `verified_merge_sha`, а `git merge-base --is-ancestor` подтверждает его
   вхождение в SHA ручного выпуска.
5. Preimage state совпадает побайтно; любое изменение после снимка требует
   построить новый манифест и повторить проверку.

Только после этого инструмент создаёт отдельный output state и audit record с
digest манифеста, release SHA, временем, старой/новой checksum и числом `28`.
Он не выбирает waits эвристически, не делает broker POST и не пишет live файл.
Оператор отдельно останавливает Pilot, повторно сверяет preimage, делает
восстановимую копию, атомарно устанавливает output и запускает Pilot. Штатный
completed-recovery создаёт ровно 28 receipts/finalizations и один done-outbox;
повторное применение того же audit id является no-op. Без доказательства
ручного выпуска операция завершается ненулевым кодом и не создаёт output.

Реальные файлы: `ops/reconcile-factory-delivery-waits.py`,
`ops/test-reconcile-factory-delivery-waits.py`,
`ops/reconciliation/factory-release-orphaned-28-waits.json`,
`pilot/pilot.py`, `pilot/test_pilot.py`.

## Последовательный план

1. Исправить installer и release generation inventory на Pilot drop-in,
   безопасно убрать legacy server drop-in и покрыть reload/restart fixture.
2. Разделить в broker code-owned executable mapping: Factory release/rollback
   направить прямо в fixed release driver, не меняя adapters других проектов.
3. Добавить failure outbox/journal event до отправки уведомления и recovery,
   сохранив terminal `failed` и незавершённые waits.
4. Уточнить безопасную dashboard projection текущего/последнего failed и
   закрепить owner-facing отображение в Overview.
5. Реализовать read-only-by-default reconciliation tool и негативные fixture
   для 27/29 waits, дублей, несовпадающего preimage/SHA, non-ancestor и
   незавершённого release journal.
6. Сформировать из подтверждённого production snapshot отдельный манифест с
   ровно 28 явными записями; не применять его до подтверждения ручного выпуска.
7. Запустить целевые shell, Go, Python и UI-тесты. Живую сверку выполнять лишь
   отдельным операторским действием по описанной stop/backup/apply/restart
   процедуре.

## Критерии приёмки

| Сценарий | Проверяемый результат |
| --- | --- |
| Доступ к broker | Installer создаёт `SupplementaryGroups=factory-release` только в новом Pilot drop-in, делает `daemon-reload` и restart `factory-pilot.service`; fixture не создаёт server drop-in. |
| Generation/rollback | Factory release inventory и bootstrap используют Pilot drop-in, а восстановление поколения возвращает согласованный файл и состояние служб. |
| Factory executable | POST с `fx-factory-release` запускает fixed `/usr/local/lib/fx-factory-release <sha>` без shell и `sudo`; rollback использует тот же driver с `--rollback`. |
| Изоляция adapters | Tarser adapters сохраняют прежний fixed `/usr/local/bin/fx` и argv; неизвестный adapter/невалидный SHA отклоняются. |
| Failure durability | После любого broker terminal failure Pilot сначала сохраняет `failed` и один `<generation>:failed` outbox item; restart до/после journal/notify не создаёт второй logical event. |
| Незавершённые waits | Failure не создаёт delivery receipt, не вызывает `mark_final(true)` и не меняет waits на completed. |
| Overview | Текущий или последний failed состав виден как человеческая ошибка с названиями работ; SHA, PID, generation/task/operation id отсутствуют в JSON и DOM. |
| Ровно 28 | Reconciliation принимает только точное равенство manifest и orphan wait set из 28 уникальных записей; 27, 29, duplicate, extra и missing завершаются без output. |
| Доказанный выпуск | Каждый verified merge является ancestor одного SHA, совпавшего в release-info/current manifest; release journal завершён, state preimage не изменился. |
| Безопасное применение | Tool не пишет live state и не вызывает broker; повтор audit id — no-op. Установка output выполняется оператором после stop/backup и не входит в deploy. |
| Область | Не меняются SQLite/API protocol, `NoNewPrivileges`, чужие adapters и live state в автоматической поставке. |

## Тест-план

- `bash ops/test-install-project-release-broker.sh`: Pilot drop-in, legacy
  cleanup, daemon reload, порядок broker/Pilot restart и повторная установка.
- `bash ops/test-fx-factory-release.sh`: generation inventory, bootstrap и
  rollback содержат fixed Pilot drop-in и не возвращают ошибочный server
  target.
- `go test ./internal/releasebroker`: table-driven executable+argv allowlist,
  direct Factory driver, неизменные другие adapters, exit status и отсутствие
  shell/произвольного executable из request.
- `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests
  pilot.test_pilot.ReleaseTrainDashboardTests`: failure crash boundaries,
  один journal/notify, ноль receipts/finalization и безопасная проекция
  current/last failed.
- `npm --prefix web test -- --run src/Overview.test.ts`: current failure,
  previous failure после N+1 и отсутствие SHA/PID/internal id в DOM.
- `python3 ops/test-reconcile-factory-delivery-waits.py`: валидные 28
  synthetic waits дают адресный output; все mismatch/evidence/preimage случаи
  fail closed; input/live state остаются неизменными.
- Перед передачей: `git diff --check`; полный проектный набор остаётся этапу
  Verify, а reconciliation на живом хосте здесь не выполняется.

## Риски и решения

- Supplementary group применяется только при новом процессе Pilot. Решение:
  обязательный restart после daemon reload и fixture порядка systemctl.
- Удаление старого server drop-in может оставить разрыв при сбое. Решение:
  сначала атомарно установить и проверить Pilot drop-in, затем убрать legacy;
  generation snapshot хранит правильный target для rollback.
- Общая тестовая подмена executable может скрыть повторный вызов `fx`.
  Решение: отдельные seams и тест точного executable+argv для каждого adapter.
- Crash между фиксацией failure и уведомлением может дать дубль push.
  Решение: durable deterministic event и deduplicated local journal; внешний
  transport остаётся at-least-once, чего нельзя честно превратить в exactly-once.
- Ошибочное завершение 28 waits хуже их зависания. Решение: set equality,
  per-wait ancestry, release metadata, завершённый journal, preimage checksum,
  output-only режим и восстановимая копия перед ручным применением.
- Реальные 28 идентификаторов не должны угадываться из текущего репозитория.
  Решение: манифест формируется только из подтверждённого production snapshot;
  отсутствие снимка или release evidence блокирует операцию, а не ослабляет
  проверку.

## Карточка работы

`knowledge/cards/CARD-0112-auto-release-broker-access-and-failure-visibility.md`

## Готово, когда

ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/Overview.tsx
ГОТОВО-КОГДА: файл web/src/Overview.test.ts
ГОТОВО-КОГДА: файл ops/reconcile-factory-delivery-waits.py
ГОТОВО-КОГДА: файл ops/test-reconcile-factory-delivery-waits.py
ГОТОВО-КОГДА: файл ops/reconciliation/factory-release-orphaned-28-waits.json
ГОТОВО-КОГДА: команда python3 ops/test-reconcile-factory-delivery-waits.py
