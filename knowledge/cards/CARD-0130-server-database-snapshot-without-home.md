# Сервер создаёт снимок базы без домашней папки

Implementation commit: 200c092c18683e004cad07a67f61e70b3ae59dda — явный CLI backup выполняется до поиска домашней папки и bootstrap-конфигурации.

## HEAD

Status: Implemented and verified — awaiting Review.

Branch: `factory/e3e7ec42-5af-08d9dabe-3e7`.

Implementation commit: `200c092c18683e004cad07a67f61e70b3ae59dda`.

What changed: `factory-server -database SOURCE -backup DEST` создаёт автономный снимок без `HOME`, `FACTORY_DATA_HOME` и `FACTORY_V2_DATA_HOME`; остальные режимы сохраняют прежнюю инициализацию.

Evidence: `go test -count=1 ./...` и `go build ./...` — PASS; целевой `go test ./cmd/factory-server` — PASS; форматирование и `git diff --check` — чистые.

One next action: провести Review запушенного кандидата относительно свежего remote default branch.

## LOG

### 2026-08-13 — Implement

- Кандидат заново собран от свежего `origin/main`; перенесены только серверная реализация и её тесты.
- `factory-server -database SOURCE -backup DEST` запускает создание снимка без домашней папки; subprocess-тест проверяет четыре формы CLI, автономность снимка и неизменность источника.
- `go test ./cmd/factory-server`, `go test -count=1 ./...`, `go build ./...`, `gofmt -l` и `git diff --check` завершились успешно.

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
