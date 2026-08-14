# Сервер создаёт снимок базы без домашней папки

Implementation commit: 7cf0368f7d2a0daf855a357f167d6f5fc67eedd3 — явный CLI backup выполняется до поиска домашней папки и bootstrap-конфигурации.

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/2900277a-169-836b7302-c15`.

Implementation commit: `7cf0368f7d2a0daf855a357f167d6f5fc67eedd3`.

What changed: `factory-server -database SOURCE -backup DEST` создаёт автономный снимок без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`; остальные режимы сохраняют прежнюю инициализацию.

Evidence: pinned-кандидат `2e00631ca88c0e0247e968acf8213815314e1871` проверен относительно remote default `ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5`; полный `go test -count=1 ./...` и `go build ./...` — PASS; форматирование и `git diff --check` — чистые; поставка содержит только три заявленных файла.

One next action: выполнить слияние после проверки владельцем.

## LOG

### 2026-08-13 — Implement

- Реализация и тесты перенесены с предыдущей ветки на свежий `origin/main`.
- Subprocess-тест запускает настоящий сервер без домашних переменных, проверяет четыре формы флагов, автономность снимка и неизменность источника.
- Целевая проверка, полный `go test -count=1 ./...`, `go build ./...`, `gofmt -l` и `git diff --check` завершились успешно.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Явный `-database` вместе с `-backup` не требует домашнюю папку | `go test -count=1 ./...`; `TestBackupCLICreatesSnapshotWithoutHome` | PASS: subprocess запускается без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME` во всех четырёх формах флагов и создаёт снимок |
| Снимок автономен и источник не изменяется | тот же subprocess-тест | PASS: есть база и control-plane marker назначения, нет `-wal`/`-shm`, байты источника и marker совпадают до и после |
| Соседние режимы сервера не регрессировали | полный `go test -count=1 ./...` | PASS: все пакеты, включая проверки restore, обычного выбора базы, bootstrap и legacy-state validation |
| Поставка ограничена заявленным объёмом | `git diff --name-status ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5...2e00631ca88c0e0247e968acf8213815314e1871` | PASS: только `cmd/factory-server/main.go`, `cmd/factory-server/main_test.go`, эта карточка |
| Сборка и качество дерева | `go build ./...`; `gofmt -l cmd/factory-server/main.go cmd/factory-server/main_test.go`; `git diff --check` | PASS: сборка успешна, `gofmt` без вывода, whitespace-проверка без ошибок |
