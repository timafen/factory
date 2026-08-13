# CARD-0149 — Сервер не требует домашнюю папку при снимке базы

Implementation commit: 822aa0604f05c52bdcc9444dd7305787b70dbaee — зафиксирована спецификация раннего backup-пути без HOME и сквозного CLI-регрессионного контракта.

Статус: Specification повторно подтверждена по свежему `origin/main`;
карточка передаётся в Implement + Test.

## Результат для владельца

`factory-server -database SOURCE -backup DEST` должен создавать standalone
SQLite snapshot и обязательный marker при отсутствии `HOME`, если исходная и
целевой пути переданы явно. Это устраняет зависимость служебного snapshot от
домашнего каталога; временная подстановка `HOME` в release-драйвере пока
остаётся без изменений.

## Спецификация

`knowledge/specs/server-database-snapshot-without-home.md`

## Область реализации

- `cmd/factory-server/main.go` — раннее распознавание связки backup и явного
  CLI database до вычисления home/bootstrap.
- `cmd/factory-server/main_test.go` — настоящий CLI subprocess без трёх
  домашних переменных, все четыре формы `database`, marker/sidecar/source
  проверки.

Не менять `cmd/factory-server/config.go`, `internal/controlplane/recovery.go`,
`ops/fx-factory-release`, обычный запуск, restore, bootstrap precedence и
legacy-защиту.

## Критерии приёмки

1. Полный CLI завершается с кодом 0 без `HOME`, `FACTORY_DATA_HOME` и
   `FACTORY_V2_DATA_HOME`.
2. Работают `-database`, `--database`, `-database=`, `--database=`; создаются
   база и `.v2-control-plane`, sidecar-файлы отсутствуют.
3. Source и его marker не меняются; backup без явного database по-прежнему
   использует текущий default/bootstrap путь.
4. Новый тест вызывает бинарь, а не только `runRecoveryMode`.

## Обязательная проверка

`go test ./cmd/factory-server -run '^TestBackupCLICreatesSnapshotWithoutHome$' -count=1`

Следующий исполнитель сначала реализует только два файла области, затем
выполняет целевую проверку, controlplane-регрессию, полный Go-набор и smoke с
unset домашними переменными.
