# Безопасный выпуск Factory: согласованный снимок и полный откат

## Цель и влияние на владельца

Это спецификация worker-discovered high-risk finding, а не ручное предложение
владельца. Production сейчас не rollback-ready: сохранённый снимок отстаёт от
живой схемы, штатный `fx factory rollback` возвращает только сервер,
`factory-worker.prev` не является долговечным артефактом, а процессы, файлы и
`factory-current.json` могут описывать разные выпуски. Миграции в `docs/release.md`
явно forward-only; на текущем `main` последняя — 026, поэтому Pilot остаётся
выключенным, а выпуск с будущей 027 запрещён до реализации этой работы.

Владелец получает один fail-closed выпуск: до изменения системы он видит
проверенный снимок базы и полный неизменяемый комплект прежнего выпуска; после
успеха — правдивый статус одного SHA. Обычный rollback возвращает весь код,
службы и метаданные. Восстановление БД остаётся отдельной, явно подтверждаемой
операцией высокого риска и никогда не запускается автоматически.

## Технический подход и реальные файлы

### Границы транзакции выпуска

- В `ops/fx-factory-release` после сборки/тестов, но до установки broker,
  provision, бинарей, control или brain, взять неблокирующий release lock и
  выполнить preflight. Разрешить только известный текущий выпуск: каждый
  активный MainPID всех `$SERVER_SERVICE`/`$WORKER_SERVICES`, Pilot и intake
  сопоставляется с `/proc/<pid>/exe`, unit `ExecStart` и SHA-256 файла. Суффикс
  ` (deleted)`, отсутствующий PID/exe, неизвестный хеш/версия, смешанные
  server/worker, отсутствующий полный rollback-комплект или несовпадающий
  manifest означают отказ до первой мутации.
- Из текущего установленного `factory-server` вызвать существующий режим
  `-database <live> -backup <fresh-path>`. Он использует SQLite online
  `VACUUM INTO`, `integrity_check`, непрерывный `schema_migrations` ledger и
  сравнение реальной схемы с миграциями текущего бинаря
  (`cmd/factory-server/main.go`, `internal/controlplane/recovery.go`). Повторно
  открыть снимок read-only, проверить отсутствие `-wal`/`-shm`, ledger=26 для
  первого допуска к 027, schema digest, размер и SHA-256. Источник БД получать
  из тех же server config/аргументов, что systemd, а не из нового default.
- На недостаток места отказать до backup/build публикации: свободно не меньше
  размера live DB + полного текущего и кандидатного комплекта + 25% запаса;
  проверить inode, один filesystem для каждого atomic rename, реальные
  root/factory-owned каталоги без symlink и `umask 077`. Снимки/manifest — 0600,
  исполняемые файлы — 0755; каталоги поколений — 0700/0750 согласно читателю.
- В `$REL/generations/<release-id>/` сначала собрать staging-поколение:
  `factory-server`, `factory-worker`, `factory-release-broker`, `ops/fx`,
  `ops/fx-factory-release`, устанавливаемые `pilot/*` и `intake/*`, а также
  backup и JSON manifest. Manifest содержит формат, release-id, candidate/ref/
  source SHA, время, все целевые пути, uid/gid/mode/size/SHA-256, DB path,
  snapshot hash/size/schema digest/ledger, unit names, active MainPID/exe/hash и
  состояния служб до выпуска. Канонический JSON и его SHA-256 неизменяемы;
  поколение публикуется atomic rename и после публикации не редактируется.
- Остановить worker units, Pilot/intake при их изменении, затем сервер. Ставить
  server/worker только парой из опубликованного поколения через подготовленные
  sibling `.new`, fsync и rename; до запуска проверить оба хеша. Journal
  `prepared|old-stopped|pair-installed|services-started|committed` с fsync
  закрывает crash boundaries: новый запуск сначала завершает recovery к
  последнему committed поколению и не строит новый кандидат. Ни в одной
  промежуточной точке mixed pair не запускается.
- Broker, control и brain устанавливать из того же поколения, сохраняя полный
  набор старых файлов и состояния units. Успех требует server health, свежей
  регистрации каждого worker identity, нужного состояния Pilot/intake/broker
  и повторного `/proc`/hash сопоставления. Только затем atomic rename публикует
  указатель current и новый правдивый `factory-current.json`, содержащий
  release-id, manifest hash и candidate SHA. Ошибка/сигнал вызывает полный
  code/service/metadata rollback; статус явно сообщает фазу и итог.

### Полный rollback и отдельное восстановление БД

- В `ops/fx` команда `fx factory rollback` под тем же lock выбирает только
  проверенное committed предыдущее поколение, останавливает затронутые units,
  возвращает server+worker+broker+control+brain/intake, прежние enable/active
  states и прежние current/release-info, затем выполняет те же health,
  registration и process/hash проверки. При сбое оставляет journal и печатает
  точную безопасную ручную процедуру; частичный успех не объявляется откатом.
- Если ledger уже несовместим со старым сервером (в частности, после 027),
  rollback возвращает файлы, metadata и записанное желаемое состояние units,
  но держит несовместимые units остановленными со статусом
  `db_restore_required`. Исходные active states восстанавливаются только после
  отдельного успешного DB restore; это часть полного, но двухоперационного
  отката, а не автоматическая мутация базы.
- Автоматический rollback **не трогает БД**. Отдельная команда восстановления
  требует остановленных Factory units, точный snapshot path + manifest hash,
  интерактивное подтверждение (или отдельный явный automation token), свободный
  новый destination и вызов `factory-server -restore`. Она никогда не
  перезаписывает live DB: сначала создаёт и проверяет восстановленную копию,
  сохраняет live DB как immutable failed-generation, затем одним rename меняет
  путь, проверяет ledger/schema/integrity/hash и лишь после этого позволяет
  запуск совместимого старого комплекта. Любая неоднозначность — отказ.
- Хранить минимум два committed комплекта и связанные DB snapshots, не менее
  14 дней; никогда не удалять current, previous, поколение из journal или
  единственный pre-027 snapshot. Retention запускается только после commit,
  проверяет manifest/hash и место; удаление логируется человекочитаемо.

## Последовательный план

1. Добавить в `ops/fx-factory-release` preflight процессов, места, прав,
   текущего manifest и обязательный валидированный online backup до миграции.
2. Ввести поколение, канонический immutable manifest, fsync-журнал фаз и
   recovery после прерывания; перенести все устанавливаемые release/brain/
   metadata артефакты под единый набор хешей.
3. Перестроить установку и автоматический rollback как остановленную транзакцию
   полного комплекта с восстановлением прежних unit states и metadata.
4. Расширить `ops/fx`: правдивые human-readable `status/release-info`, полный
   code rollback и отдельный подтверждаемый DB restore без overwrite.
5. Расширить shell fixture и добавить реальную systemd/process интеграцию:
   deleted inode, неизвестная версия, пропавший artifact, mixed pair, падение
   после каждой journal-фазы, рестарт и идемпотентное recovery.
6. Добавить SQLite сценарий 026→027: online backup под записью, manifest tie,
   применение forward-only 027, полный code rollback без изменения DB и
   отдельный restore в новый файл с проверкой данных/ledger/schema.
7. Добавить retention/permissions/disk тесты и русские сообщения успеха,
   отказа, auto-rollback, manual DB recovery; лишь после PASS разрешить
   отдельную реализацию миграции 027 и включение Pilot.

## Критерии приёмки

1. До первой мутации существует проверенный standalone SQLite snapshot,
   однозначно связанный с live path, ledger/schema, candidate SHA и manifest.
2. Deleted-inode процесс, неизвестный или смешанный выпуск, отсутствующий
   rollback artifact, неверный hash/owner/mode, недостаток disk/inode либо
   незавершённый journal блокирует выпуск с понятной причиной.
3. Manifest охватывает server, worker, broker, release/control scripts,
   brain/intake, metadata и фактические process identities; published manifest
   неизменяем и проверяется перед release/rollback/retention.
4. Server и все workers никогда не запускаются смешанной парой. Metadata
   меняется только после health, свежих worker heartbeats и проверки хешей
   реально запущенных процессов.
5. Ошибка или interruption в каждой фазе детерминированно возвращает полный
   прежний комплект, metadata и совместимые active/enabled states либо
   оставляет явный recoverable journal без ложного сообщения об успехе. При
   несовместимом ledger исходное active state записано, units безопасно
   остановлены до отдельного DB restore и итог не называется успешным.
6. `fx factory rollback` возвращает весь комплект и проверяет его. База при
   этом byte-for-byte не меняется; после отдельного успешного restore команда
   завершения отката возвращает записанные состояния служб.
7. DB restore возможен только отдельной high-risk командой, не перезаписывает
   существующий файл, сохраняет failed DB и до старта проверяет integrity,
   contiguous ledger, schema и совместимость выбранного поколения.
8. Retention сохраняет current+previous и pre-027 snapshot минимум 14 дней;
   права, fsync, место и cleanup устойчивы к повторному запуску.
9. Status/notifications по-русски называют candidate/current/previous SHA,
   snapshot/manifest, фазу, службы и действие владельца; Pilot не включается и
   production не изменяется этой работой.

## Тест-план

- `ops/test-fx-factory-release.sh`: изолированные сценарии preflight,
  manifest, порядка backup→mutation, пары, metadata commit, полного rollback,
  retention, disk/permission отказов и interruption каждой фазы.
- Новый `ops/test-factory-release-systemd.sh`: запуск временных unit-файлов
  через доступный systemd fixture (иначе явный SKIP только вне CI), реальные
  MainPID и `/proc/<pid>/exe`, включая заменённый deleted inode; доказать отказ
  mixed/unknown процессов и восстановление active/inactive states.
- `internal/controlplane/recovery_test.go` и release fixture: реально создать
  SQLite 026, писать параллельно online backup, проверить snapshot, применить
  тестовую 027, доказать, что code rollback не меняет БД, затем восстановить в
  fresh path и сравнить данные, ledger, schema digest и отсутствие sidecars.
- Перед передачей: `bash -n` изменённых shell-файлов, `go test` recovery,
  обязательный release test и `git diff --check`.

## Риски и решения

- Два rename не дают общей filesystem-атомарности: службы остановлены, journal
  fsync-нут перед каждым rename, а запуск разрешён только после проверки пары;
  recovery устраняет crash window.
- Online backup может устареть сразу после создания: он является согласованной
  точкой восстановления, а manifest фиксирует время/ledger/hash; для ручного
  DB restore владелец осознанно принимает потерю записей после этой точки.
- Старый бинарь несовместим с 027: обычный rollback возвращает код, но не
  запускает несовместимый сервер; статус требует отдельного DB restore. Это
  безопаснее автоматического разрушительного overwrite.
- Разные service layouts: manifest фиксирует полный раскрытый список units,
  MainPID и состояния; неизвестный unit/process блокирует выпуск, а не
  угадывается.
- Retention может удалить единственное спасение: current, previous, journal и
  pre-027 защищены независимо от возраста; cleanup работает только по
  проверенным committed поколениям.

## Карточка работы

`knowledge/cards/CARD-0088-safe-release-snapshot-full-rollback.md`

## Точный план реализации и следующая операция

Файлы ниже — исчерпывающий минимальный implementation scope. Сначала реализовать
manifest/preflight/backup и crash-safe transaction, затем полный rollback и
отдельный restore, после чего пройти fixtures. Следующее действие одно:
передать CARD-0088 в Implement; до его приёмки не выпускать migration 027 и не
включать Pilot.

Обязательная команда ниже становится доказательством только после расширения
`ops/test-fx-factory-release.sh` сценарием, который создаёт online snapshot при
параллельной записи, связывает его hash/ledger/schema с manifest, принудительно
роняет выпуск после установки пары и подтверждает возврат всего прежнего
комплекта, unit states и metadata при byte-for-byte неизменной live DB. Один
лишь успешный запуск прежнего набора сценариев критерий не закрывает.

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/fx
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-factory-release-systemd.sh
ГОТОВО-КОГДА: файл internal/controlplane/recovery_test.go
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
