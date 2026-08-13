# Сервер создаёт снимок базы без домашней папки

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/f11d2e97-9bc-4a16aef5-e39`.

Implementation commit: 633abb73257d9315d1e8600eb4fea144a773daa8 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` теперь сразу использует явно заданные пути. Обычный запуск, restore и backup без явной базы сохраняют прежнюю подготовку defaults.

Evidence: после закрепления свежего remote `main` (`99701704b37e8740db3fdbe38c0193917570da5c`) и кандидата (`ba97a673ba75e18a65c05cf02dfe20b6cd78b52b`) полный `go test -count=1 -timeout 5m ./...`, `go build ./...` и целевой subprocess-тест завершились успешно. Четыре формы CLI без `HOME` создали автономный снимок и не изменили исходную базу.

One next action: человеку выполнить merge этой ветки в `main`.

## LOG

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Явные source и backup обходят домашнюю папку | `go test -count=1 -v ./cmd/factory-server -run '^TestBackupCLICreatesSnapshotWithoutHome$'` | PASS: `-flag value`, `--flag value`, `-flag=value`, `--flag=value` успешно создали снимок без `HOME` и bootstrap-конфигурации |
| Снимок автономен, источник не изменён | тот же subprocess-тест | PASS: backup и marker — обычные файлы, у backup отсутствуют WAL/SHM; source и marker совпали побайтно с состоянием до backup |
| Грамматика и смежные defaults сохранены | целевой набор `TestBackupWithExplicitDatabaseHonorsFlagGrammar`, `TestBackupModeRejectsMissingSourceWithoutCreatingState`, `TestDefaultDatabasePath…`, `TestServerBootstrapConfig…` | PASS: некорректные и позиционные флаги не обходят подготовку; отсутствие источника, defaults и bootstrap ведут себя как прежде |
| Полный набор и сборка | `go test -count=1 -timeout 5m ./...`; `go build ./...` | PASS; PASS |
| Граница поставки | изолированное сравнение `99701704b37e8740db3fdbe38c0193917570da5c...ba97a673ba75e18a65c05cf02dfe20b6cd78b52b` | Только `cmd/factory-server/main.go`, `cmd/factory-server/main_test.go`, эта карточка |

### 2026-08-13 — Implement

- Восстановлен ранее проверенный кодовый коммит в назначенной ветке без переноса посторонних файлов.
- Целевой subprocess-тест снова подтвердил четыре формы CLI backup без `HOME`; источник остался неизменным, снимок автономен.
- Полный `go test -count=1 -timeout 5m ./...` и `go build ./...` завершились успешно.

### 2026-08-13 — Implement

- Добавлен ранний разбор намерения по грамматике Go `flag` с остановкой на позиционном аргументе.
- Реальный бинарь проверен для четырёх форм `database`/`backup` без `HOME`, data-home переменных и доступного bootstrap-файла.
- Snapshot и marker создаются без WAL/SHM, исходная база и её marker не изменяются.
- Полный `go test ./...` и `go build ./...` завершились успешно.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Кандидат сравнивается со свежей удалённой базой | `git ls-remote --symref origin HEAD`; изолированный fetch `99701704b37e8740db3fdbe38c0193917570da5c...cd7744ca50a7200d4709e0b41a74fffc86fa451a` | Default ref — `refs/heads/main`; обе fetched SHA совпали с remote |
| Снимок явной базы работает без домашней папки во всех четырёх формах CLI | `go test -count=1 -v ./cmd/factory-server -run 'TestBackupCLICreatesSnapshotWithoutHome|TestBackupWithExplicitDatabaseHonorsFlagGrammar|…'` | PASS; отдельные subprocess-кейсы `-flag value`, `--flag value`, `-flag=value`, `--flag=value` прошли |
| Источник остаётся неизменным, снимок автономен | `TestBackupCLICreatesSnapshotWithoutHome` | PASS; база и marker совпали побайтово, у снимка нет WAL/SHM |
| Смежные default/bootstrap и ошибка отсутствующего источника сохранены | целевой набор тестов `TestBackupModeRejectsMissingSourceWithoutCreatingState`, `TestDefaultDatabasePath…`, `TestServerBootstrapConfig…` | PASS |
| Полный набор и сборка | `go test -count=1 -timeout 5m ./...`; `go build ./...` | PASS; PASS |
| Область изменений | `git diff --name-only 99701704b37e8740db3fdbe38c0193917570da5c...cd7744ca50a7200d4709e0b41a74fffc86fa451a` | Только `cmd/factory-server/main.go`, `cmd/factory-server/main_test.go`, эта карточка |
