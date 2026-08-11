Implementation commit: c80569c53d59ae2d916284ac93ce9583ec59f038 — экран восстанавливается после конфликта, а atomicWrite сохраняет действующую конфигурацию при сбое записи

# CARD-0068 — Безопасное восстановление настроек после конфликта

## HEAD

- Status: Implemented — awaiting repeat review.
- Branch: `factory/e9dee141-2a0-27797158-1e3`.
- Implementation commit: `c80569c53d59ae2d916284ac93ce9583ec59f038` — восстановление после конфликта и безопасная запись настроек.
- What changed: после `409` владелец загружает свежие настройки; `atomicWrite` отклоняет ошибку и короткую запись, закрывает и удаляет временный файл, не заменяя действующую конфигурацию.
- Evidence: реальные write-error/short-write ветви `atomicWrite` и закрытие/очистка проверены; control-plane PASS, Settings 9/9 PASS, typecheck/lint/build PASS, `go build ./...` PASS.
- One next action: повторно запустить Review для `/settings`.

## LOG

### 2026-08-11 — Implement

Основной экран и API уже находились в `main`. Узкая поставка добавила русское
действие восстановления после конфликта версии и недостающие проверки обещаний:
перестановка `brain_chain` сохраняет notes, запись атомарно заменяет inode, а
missing/oversized/invalid файл и сбой записи не повреждают прежние данные.

Доказательства: целевой `go test ./internal/controlplane` — PASS; `Settings.test.tsx`
— 9/9 PASS; TypeScript, focused ESLint, production build и `go build ./...` — PASS.

### 2026-08-11 — Implement

После замечания Review тестовая подмена всего сохранения заменена внедрением только
операции записи во временный файл. Production `atomicWrite` теперь проверяет ошибку
и длину записи, а при обоих сбоях закрывает и удаляет временный файл до rename;
тест подтверждает также неизменность действующей конфигурации.

Доказательства: `go test ./internal/controlplane` — PASS, включая write error и
short write; `Settings.test.tsx` — 9/9 PASS; web typecheck/lint/build и
`go build ./...` — PASS.
