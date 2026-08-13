# Сервер создаёт снимок базы без домашней папки

Implementation commit: 3090866634059f02a6fc5ae5d2ada869e1662a97 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

## HEAD

Status: Verified PASS — ready to deliver.

Branch: `factory/7276dbb0-e0b-afc197a8-73b`.

Implementation commit: 3090866634059f02a6fc5ae5d2ada869e1662a97 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` обрабатывает снимок до поиска домашней папки. Обычный запуск и другие режимы по-прежнему загружают обычные defaults и bootstrap.

Evidence: `go test ./...`, `go build ./...` и `go test ./cmd/factory-server` завершились успешно; subprocess-проверка покрывает четыре формы CLI без `HOME`, автономность снимка и неизменность источника.

One next action: передать опубликованную ветку на review.

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

### 2026-08-13 — Implement

- Чистая ветка `factory/7276dbb0-e0b-afc197a8-73b` собрана от свежего `origin/main`; перенесены только сервер, тест и эта карточка.
- Коммит реализации `3090866634059f02a6fc5ae5d2ada869e1662a97` запускает явный backup до вычисления домашней папки.
- Проверено: `go test ./cmd/factory-server`, `go test ./...` и `go build ./...` — успешно; область — три ожидаемых файла.
