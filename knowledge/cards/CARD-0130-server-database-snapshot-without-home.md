# Сервер создаёт снимок базы без домашней папки

Implementation commit: 1e4f7316513c7c8b329dfe01c8c43a41e5ee38cc — явный CLI backup выполняется до поиска домашней папки и bootstrap-конфигурации.

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/aaac33cd-686-712a01d8-21f`.

Implementation commit: `1e4f7316513c7c8b329dfe01c8c43a41e5ee38cc`.

What changed: `factory-server -database SOURCE -backup DEST` создаёт
автономный снимок без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`.
Остальные режимы сохраняют прежнюю инициализацию.

Evidence: полный `go test -count=1 ./...` — PASS; полный `go build ./...`
— PASS; целевая subprocess-проверка четырёх форм CLI без домашней папки — PASS.

One next action: влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

- Перенесён проверенный кандидат CARD-0124 без альтернативной реализации.
- Ранний recovery-путь включается только для непустого `-backup` и явно
  посещённого `-database`; грамматику разбирает стандартный `flag.FlagSet`.
- Subprocess-тест собрал настоящий сервер и подтвердил четыре формы флагов без
  домашних переменных, автономность снимка и неизменность файлов источника.
- `go test -count=1 ./cmd/factory-server -run
  '^TestBackupCLICreatesSnapshotWithoutHome$'`, `go test ./...` и
  `go build ./...` завершились успешно.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Явный снимок не требует домашнюю папку | `go test -count=1 ./cmd/factory-server -run '^(TestBackupCLICreatesSnapshotWithoutHome|TestBackupWithExplicitDatabaseHonorsFlagGrammar)$'` | PASS: subprocess запускает сервер без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`. |
| Принимаются четыре формы флагов | Та же subprocess-проверка | PASS: `-database VALUE -backup VALUE`, `--database VALUE --backup VALUE`, а также обе формы с `=`. |
| Снимок автономен, источник не меняется | Та же subprocess-проверка | PASS: для снимка есть оба регулярных файла без WAL/SHM; байты исходной базы и маркера неизменны. |
| Нет регрессий проекта | `go test -count=1 ./...`; `go build ./...` | PASS: полный набор тестов и сборка завершились успешно. |
