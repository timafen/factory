# CARD-0089 — Ошибка записи итога удерживает слот выпуска

Implementation commit: c3c6edd655f9359dde7671f4c9fcc3f1c06e68f5 — broker не запускает следующий выпуск после несохранённого terminal status.

## HEAD

- Status: Implemented and verified.
- Branch: `factory/6b6dfd9a-9f9-601f8c66-ddc`.
- Implementation commit: c3c6edd655f9359dde7671f4c9fcc3f1c06e68f5 — неоднозначный итог оставляет глобальный release-slot занятым.
- What changed: Ошибка durable-записи terminal status больше не разрешает параллельный следующий выпуск.
- Evidence: `go test -race -count=1 ./internal/releasebroker` → OK; fixture получил HTTP 409 на второй выпуск и сохранил один вызов executor.
- Evidence: `just check` → Go-набор OK, первоначально остановлен отсутствующим `eslint`; после `npm ci`, `just ui-check` → 14 файлов/158 тестов OK; `just build` → OK.
- Next action: Review code and regression fixture.

## LOG

### 2026-08-11 — Implement

Terminal persist remains the authoritative completion boundary. A real filesystem
write failure now keeps the privileged release slot reserved, and the regression
proves that neither success nor a second physical delivery can pass that boundary.
