# Сервер создаёт снимок базы без домашней папки

Implementation commit: 6a9fbcf9efc5556df410c6d89d4e7b027c42fdbe — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

## HEAD

Status: Verified PASS — awaiting human merge.

Branch: `factory/8a886f3e-7bb-09ea3d08-3f9`.

Implementation commit: 6a9fbcf9efc5556df410c6d89d4e7b027c42fdbe — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` обрабатывает снимок до поиска домашней папки. Обычный запуск и другие режимы по-прежнему загружают обычные defaults и bootstrap.

Evidence: полный `go test ./...` и `go build ./...` завершились успешно; subprocess-проверка покрывает четыре формы CLI без `HOME`, автономность снимка и неизменность источника.

One next action: влить проверенную поставку в `main`.

## LOG

### 2026-08-13 — Implement

- Явный `-database` вместе с `-backup` теперь выполняет recovery mode до вычисления data-root, поэтому домашняя папка не требуется.
- Добавлены проверки всех четырёх поддержанных форм флагов без `HOME`, автономности снимка и неизменности исходной базы.
- Проверено: `go test ./cmd/factory-server`; `go build ./...` — успешно.

### 2026-08-13 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Явный backup без домашней папки | `go test ./cmd/factory-server` | PASS: четыре формы флагов создают снимок без `HOME` и конфигурации |
| Полный набор тестов | `go test ./...` | PASS: все пакеты зелёные |
| Сборка проекта | `go build ./...` | PASS |
| Область изменения | pinned `main...candidate` diff | PASS: три ожидаемых файла |
