# Сервер создаёт снимок базы без домашней папки

Implementation commit: 1a9a772dfbb6577bff2a786becc19dd8d3328393 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

## HEAD

Status: Implemented — ready for review.

Branch: `factory/8a886f3e-7bb-09ea3d08-3f9`.

Implementation commit: 1a9a772dfbb6577bff2a786becc19dd8d3328393 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

What changed: `factory-server -database SOURCE -backup DEST` обрабатывает снимок до поиска домашней папки. Обычный запуск и другие режимы по-прежнему загружают обычные defaults и bootstrap.

Evidence: `go test ./cmd/factory-server` и `go build ./...` завершились успешно; subprocess-проверка покрывает четыре формы CLI без `HOME`.

One next action: проверить поставку и влить её в `main`.

## LOG

### 2026-08-13 — Implement

- Явный `-database` вместе с `-backup` теперь выполняет recovery mode до вычисления data-root, поэтому домашняя папка не требуется.
- Добавлены проверки всех четырёх поддержанных форм флагов без `HOME`, автономности снимка и неизменности исходной базы.
- Проверено: `go test ./cmd/factory-server`; `go build ./...` — успешно.
