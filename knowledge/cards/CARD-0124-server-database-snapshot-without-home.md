# Сервер создаёт снимок базы без домашней папки

## HEAD

Status: Verified PASS — ожидает слияния человеком.

Branch: `factory/e6c29a46-329-daa686c1-ed7`.

Implementation commit: 633abb73257d9315d1e8600eb4fea144a773daa8 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` теперь сразу использует явно заданные пути. Обычный запуск, restore и backup без явной базы сохраняют прежнюю подготовку defaults.

Evidence: pinned diff `99701704b37e8740db3fdbe38c0193917570da5c...cd7744ca50a7200d4709e0b41a74fffc86fa451a` содержит только три заявленных файла; полный `go test -count=1 -timeout 5m ./...`, `go build ./...` и целевые проверки завершились успешно. Subprocess-тест подтвердил четыре формы CLI без `HOME`, создание автономного снимка и неизменность исходной базы.

One next action: влить проверенную ветку в `main`.

## LOG

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
