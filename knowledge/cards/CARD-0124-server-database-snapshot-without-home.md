# Сервер создаёт снимок базы без домашней папки

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/eac8c5c9-297-d0771bdc-319`.

Implementation commit: 633abb73257d9315d1e8600eb4fea144a773daa8 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` теперь сразу использует явно заданные пути. Обычный запуск, restore и backup без явной базы сохраняют прежнюю подготовку defaults.

Evidence: pinned-кандидат `97c295653dd3122c0b69904280625ff292f30c73` собран с чистым Go-кэшем; полный набор и целевые subprocess-проверки прошли. Четыре формы CLI создали автономные снимки без `HOME`, не изменив исходную базу.

One next action: человеку выполнить merge этой ветки в `main`.

## LOG

### 2026-08-13 — Implement

- Повторно проверен неизменённый кодовый снимок: четыре формы CLI создали автономный backup без `HOME`, исходная база осталась неизменной.
- Полный `go test -count=1 -timeout 5m ./...` и `go build ./...` завершились успешно.
- Утверждённый кандидат `ba97a673ba75e18a65c05cf02dfe20b6cd78b52b` опубликован как `origin/factory/46202505-dee-409e1e03-150`; удалённый SHA совпал.

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

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Кандидат закреплён относительно свежей удалённой базы | `git ls-remote --symref origin HEAD`; изолированный bare-fetch `99701704b37e8740db3fdbe38c0193917570da5c...97c295653dd3122c0b69904280625ff292f30c73` | PASS: default ref — `refs/heads/main`; обе полные SHA совпали с remote |
| Явные source и backup не требуют домашнюю папку во всех поддержанных формах CLI | `go test -count=1 -v ./cmd/factory-server -run '^(TestBackupCLICreatesSnapshotWithoutHome|TestBackupWithExplicitDatabaseHonorsFlagGrammar|…)$'` | PASS: `-flag value`, `--flag value`, `-flag=value`, `--flag=value` прошли без `HOME`, data-home переменных и доступного bootstrap-файла |
| Снимок автономен, источник не изменяется | `TestBackupCLICreatesSnapshotWithoutHome` | PASS: backup и marker — обычные файлы без WAL/SHM; source и marker после четырёх запусков побайтово равны исходным |
| Смежные default/bootstrap и ошибка отсутствующего source сохранены | `TestBackupModeRejectsMissingSourceWithoutCreatingState`, `TestDefaultDatabasePath…`, `TestServerBootstrapConfig…` | PASS: все восемь целевых верхнеуровневых тестов и их подслучаи прошли |
| Чистая сборка и полный набор | новый `GOCACHE`; `go build ./...`; новый `GOCACHE`; `go test -count=1 -timeout 5m ./...` | PASS: exit 0 за 48.30 с; exit 0 за 232.94 с, все пакеты зелёные |
| Граница и чистота поставки | pinned `git diff --name-status`, `git diff --check`, поиск debug-маркеров, `git status --short` | PASS: только `main.go`, `main_test.go` и CARD-0124; whitespace/debug/stray-файлов нет |
