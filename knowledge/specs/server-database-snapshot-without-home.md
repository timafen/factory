# Сервер создаёт снимок явно указанной базы без домашней папки

## Цель и влияние на владельца

Служебный запуск `factory-server -database SOURCE -backup DEST` должен
завершаться успешно в окружении systemd, где нет `HOME`, если оба пути заданы
в командной строке. Сейчас сервер обращается к домашнему каталогу ещё до
разбора флагов и не доходит до уже существующего безопасного SQLite snapshot.

После изменения владелец получает проверяемый standalone-снимок и marker без
временной подстановки домашнего пути в release-драйвере. Обычный серверный
запуск, выбор неявной базы, bootstrap-конфигурация, restore и legacy-защита
сохраняют нынешнее поведение.

## Технический подход и реальные файлы

### Зафиксированный контекст текущего кода

В текущем `cmd/factory-server/main.go` `run()` сначала вызывает
`defaultDatabasePath()` и `loadServerBootstrapConfig()`, а `flag.Parse()` —
только после этого. Поэтому явные `-database` и `-backup` ещё не могут
повлиять на выбор пути до обращения к домашнему каталогу. После разбора
флагов код уже передаёт значения в `runRecoveryMode`, а
`internal/controlplane.BackupDatabase` публикует проверенный SQLite-файл и
marker. Спецификация меняет только порядок подготовки CLI в этом первом
файле и закрепляет сквозную проверку; recovery-механизм повторно не
проектируется.

### Граница раннего разбора

В `cmd/factory-server/main.go` перед первым вызовом `defaultDatabasePath()`
добавить малый разборщик намерения запуска. Он должен использовать грамматику
текущего Go `flag` и распознавать только валидную последовательность флагов до
первого позиционного аргумента, а не искать подстроки. Для `database` покрыть
формы `-database SOURCE`, `--database SOURCE`, `-database=SOURCE` и
`--database=SOURCE`; для `backup` сохранить обычные раздельную и `=` формы.

Если ранний разбор подтверждает режим `backup` и явный CLI-флаг `database`,
основной запуск должен создать флаги с безопасными начальными значениями,
пропустить `defaultDatabasePath()` и `loadServerBootstrapConfig()`, затем
выполнить обычный `flag.Parse()` и использовать фактические значения после
разбора. Так явно переданный путь остаётся источником истины, а ошибки
синтаксиса и конфликт `backup`/`restore` по-прежнему выдаёт штатный разбор.
Путь recovery нужно вызвать до проверок, которым требуется `dataRoot`:
`validateLegacyServerSelection` и `validateDataRoot` не должны вычисляться в
этом специальном backup-потоке.

Особый путь ограничен именно backup с явным CLI `database`. Для обычного
запуска и для restore сначала сохраняются текущие вычисление
`defaultDatabasePath`, загрузка bootstrap и проверки выбора базы. Backup без
явного `database` также продолжает использовать `FACTORY_DATA_HOME`, затем
`FACTORY_V2_DATA_HOME` (preview alias) и затем `HOME` через существующий
`factoryDataHome`/`defaultDatabasePath`. `flag.Visit` после полного разбора
остаётся источником признака явного выбора для legacy-защиты в обычном потоке.

`runRecoveryMode` и `internal/controlplane.BackupDatabase` не менять: они уже
проверяют исходную базу, делают `VACUUM INTO`, валидируют snapshot, публикуют
его без замены существующей цели и создают
`DEST.v2-control-plane`. `ops/fx-factory-release` также не менять и не
удалять его временную подстановку `HOME`; она остаётся совместимой защитой до
отдельной работы по release-драйверу.

### Реальные файлы реализации

- `cmd/factory-server/main.go` — раннее распознавание намерения и развилка
  до home/bootstrap-зависимых вычислений; обычный и restore-пути без
  перестройки семантики.
- `cmd/factory-server/main_test.go` — сквозной CLI-регресс без HOME и
  проверки всех форм `database`, marker, sidecar-файлов и неизменности source.

`cmd/factory-server/config.go`, `internal/controlplane/recovery.go` и
`ops/fx-factory-release` являются контекстом и не входят в diff реализации.

## Последовательный план

1. Вынести тестируемое распознавание раннего recovery-намерения из
   `os.Args[1:]`, сохранив правила Go `flag` для четырёх форм `database`,
   раздельного/`=` значения `backup`, повторных флагов и позиционной границы.
2. Разделить в `run()` подготовку defaults и полный `flag.Parse`: специальный
   backup с явным CLI `database` не вызывает home/bootstrap helpers; после
   parse он проходит существующий `runRecoveryMode` и сразу завершает процесс.
3. Оставить без изменений ветки обычного запуска, restore, bootstrap
   precedence, `validateLegacyServerSelection`, `validateDataRoot` и release
   driver; проверить их существующими пакетными тестами.
4. Добавить в `cmd/factory-server/main_test.go` один полный subprocess-сценарий:
   подготовить валидную Factory SQLite-базу, собрать `factory-server`, четыре
   раза запустить бинарь с чистым окружением и проверить результаты.
5. Выполнить целевые проверки, затем `go test ./internal/controlplane -count=1`,
   полный `go test ./...`, ручной smoke без всех трёх домашних переменных и
   `git diff --check`.

Порядок выполнения реализации: сначала тест и минимальная CLI-развилка,
затем пакетные регрессии; удаление временной подстановки `HOME` в
`ops/fx-factory-release` не является частью этой работы.

## Критерии приёмки

1. Реальный бинарь `factory-server` с `-database SOURCE -backup DEST` при
   unset `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME` завершается с
   кодом 0 и сообщает о созданном snapshot.
2. Тот же CLI-путь успешно принимает `-database SOURCE`, `--database SOURCE`,
   `-database=SOURCE` и `--database=SOURCE` (с соответствующими backup-формами).
3. Для каждого запуска существуют согласованные `DEST` и
   `DEST.v2-control-plane`, отсутствуют `DEST-wal` и `DEST-shm`, а source и
   его marker побайтно не изменились.
4. При явном backup сервер не вызывает `os.UserHomeDir`, не вычисляет
   default database и не читает `FACTORY_SERVER_CONFIG`/bootstrap-файл; тест
   должен сделать `FACTORY_SERVER_CONFIG` заведомо отсутствующим, чтобы это
   было наблюдаемым условием.
5. Backup без явного `database` сохраняет приоритет `FACTORY_DATA_HOME`,
   preview alias `FACTORY_V2_DATA_HOME` и fallback к `HOME`; обычный запуск и
   restore сохраняют текущие пути и bootstrap precedence.
6. Legacy-защита по-прежнему срабатывает для неявного обычного выбора и не
   блокирует явно выбранную базу; временный обход `HOME` в
   `ops/fx-factory-release` остаётся без изменений.
7. Регрессия запускает полный CLI subprocess, а не только прямой вызов
   `runRecoveryMode`; ошибка должна воспроизводиться на старом коде из-за
   раннего обращения к домашнему каталогу.

## Тест-план

В `TestBackupCLICreatesSnapshotWithoutHome` подготовить source через
существующий `controlplane.Open`, закрыть его до запуска, сохранить хеши
source и marker, затем один раз собрать бинарь в `t.TempDir()`. Таблица из
четырёх случаев запускает настоящий бинарь через `exec.Command` с
`HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME` удалёнными и с
`FACTORY_SERVER_CONFIG` на отсутствующий путь. Для каждого случая проверяются
exit code 0, сообщение CLI, два опубликованных файла, отсутствие SQLite
sidecar-файлов и неизменность исходных хешей.

Обязательная целевая команда:

`go test ./cmd/factory-server -run '^TestBackupCLICreatesSnapshotWithoutHome$' -count=1`

Перед передачей в Verify дополнительно выполнить:

- `go test ./cmd/factory-server -count=1` — существующие default path,
  bootstrap, legacy и data-root регрессии вместе с новым CLI-тестом;
- `go test ./internal/controlplane -count=1` — неизменность recovery-контракта;
- `go test ./...` — полный Go-регресс ровно на стадии Verify;
- smoke с `env -u HOME -u FACTORY_DATA_HOME -u FACTORY_V2_DATA_HOME` на
  валидной SQLite-базе;
- `git diff --check`.

## Риски и решения

- Риск: наивный поиск `database` примет значение другого строкового флага или
  аргумент после позиционного значения. Решение: ограничить ранний разбор
  текущей flag-грамматикой, арностью известных флагов и остановкой на первом
  позиционном аргументе; все четыре формы закрепить таблицей теста.
- Риск: ранняя ветка начнёт влиять на restore или обычный server startup.
  Решение: условие должно требовать одновременно backup и явный CLI database,
  а не только наличие database; home/bootstrap и root/legacy checks оставить в
  прежнем потоке для всех остальных режимов.
- Риск: пропуск bootstrap скроет ошибку конфигурации в обычном backup.
  Решение: пропуск разрешён только когда source явно передан флагом; backup
  без него продолжает читать bootstrap после вычисления data root.
- Риск: тест докажет только прямую recovery-функцию. Решение: собирать и
  запускать отдельный бинарь, проверяя exit code, окружение, marker и source.
- Риск: обход в release-драйвере будет удалён как часть исправления. Решение:
  явно оставить `ops/fx-factory-release` вне области и проверять его отсутствие
  в diff.

## Карточка работы

`knowledge/cards/CARD-0149-server-database-snapshot-without-home.md`

ГОТОВО-КОГДА: файл cmd/factory-server/main.go
ГОТОВО-КОГДА: файл cmd/factory-server/main_test.go
ГОТОВО-КОГДА: команда go test ./cmd/factory-server -run '^TestBackupCLICreatesSnapshotWithoutHome$' -count=1
