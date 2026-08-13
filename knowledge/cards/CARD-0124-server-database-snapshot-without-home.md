# Сервер создаёт снимок базы без домашней папки

## HEAD

Status: реализовано, готово к проверке.

Branch: `factory/e6c29a46-329-daa686c1-ed7`.

Implementation commit: 633abb73257d9315d1e8600eb4fea144a773daa8 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` теперь сразу использует явно заданные пути. Обычный запуск, restore и backup без явной базы сохраняют прежнюю подготовку defaults.

Evidence: целевой subprocess-тест, пакетные тесты, `go test ./...`, `go build ./...` и ручной запуск без `HOME` завершились успешно.

One next action: проверить diff и влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

- Добавлен ранний разбор намерения по грамматике Go `flag` с остановкой на позиционном аргументе.
- Реальный бинарь проверен для четырёх форм `database`/`backup` без `HOME`, data-home переменных и доступного bootstrap-файла.
- Snapshot и marker создаются без WAL/SHM, исходная база и её marker не изменяются.
- Полный `go test ./...` и `go build ./...` завершились успешно.
