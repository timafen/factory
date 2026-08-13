# Сервер создаёт снимок базы без домашней папки

Implementation commit: dac9cbfa1cb114599b6011d8ad8ff7165881a660 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

## HEAD

Status: Implemented — awaiting review.

Branch: `factory/8e2dcf30-e06-681d9c60-c30`.

Implementation commit: dac9cbfa1cb114599b6011d8ad8ff7165881a660 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` обрабатывает снимок до поиска домашней папки. Обычный запуск и другие режимы по-прежнему загружают обычные defaults и bootstrap.

Evidence: `go test -count=1 ./cmd/factory-server` завершился успешно; subprocess-проверка покрывает четыре формы CLI без `HOME`, автономность снимка и неизменность источника.

One next action: передать опубликованную ветку на review.

## LOG

### 2026-08-13 — Implement

- Чистая ветка собрана от свежего `origin/main`; перенесены только сервер, его тесты и CARD-0124.
- Коммит реализации `dac9cbfa1cb114599b6011d8ad8ff7165881a660` запускает явный backup до вычисления домашней папки.
- Проверено: `go test -count=1 ./cmd/factory-server` — PASS; область — три ожидаемых файла.

### 2026-08-13 — Implement (delivery retry)

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

### 2026-08-13 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Явный backup без домашней папки | `go test -count=1 ./cmd/factory-server` | PASS: четыре формы флагов создают снимок без `HOME`, снимок автономен, источник не изменён |
| Сборка проекта | `go build ./...` | PASS |
| Полный набор Go | `go test ./...` из чистого архива | Не завершился: зависли тесты `internal/controlplane` и `internal/worker`, не затронутые этой поставкой |
| Область изменения | pinned `99701704b37e8740db3fdbe38c0193917570da5c...caa7bbd8e6dd54e6e230af612c2a632e20da0e47` | PASS: изменены только `main.go`, его тесты и карточка |

### 2026-08-13 — Implement

- Чистая ветка `factory/7276dbb0-e0b-afc197a8-73b` собрана от свежего `origin/main`; перенесены только сервер, тест и эта карточка.
- Коммит реализации `3090866634059f02a6fc5ae5d2ada869e1662a97` запускает явный backup до вычисления домашней папки.
- Проверено: `go test ./cmd/factory-server`, `go test ./...` и `go build ./...` — успешно; область — три ожидаемых файла.
