Implementation commit: c80569c53d59ae2d916284ac93ce9583ec59f038 — экран восстанавливается после конфликта, а atomicWrite сохраняет действующую конфигурацию при сбое записи

# CARD-0068 — Безопасное восстановление настроек после конфликта

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/e9dee141-2a0-27797158-1e3`.
- Implementation commit: `c80569c53d59ae2d916284ac93ce9583ec59f038` — восстановление после конфликта и безопасная запись настроек.
- What changed: после `409` владелец загружает свежие настройки; `atomicWrite` отклоняет ошибку и короткую запись, закрывает и удаляет временный файл, не заменяя действующую конфигурацию.
- Evidence: `just check` PASS (Go tests, static analysis, 147 UI tests, tooling and launcher); `just test-browser` PASS (19 Chromium E2E), включая сохранение `/settings` и проверку значения после reload.
- One next action: владелец проверяет доказательства и принимает решение о merge.

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

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Конфликт версии предлагает безопасное восстановление | `web/src/Settings.test.tsx` в `just check` | 9/9 Settings tests PASS; после 409 доступна загрузка свежих настроек. |
| Сбой или короткая запись не повреждает текущую конфигурацию | `go test ./...` в `just check` | PASS; тесты `atomicWrite` подтверждают закрытие и очистку временного файла и неизменность прежней конфигурации. |
| Экран реально сохраняет настройки | `just test-browser` | 19/19 Chromium E2E PASS; `/settings` отправляет PUT 200, а изменённый интервал остаётся `15` после reload. |
| Смежные функции не регрессировали | `just check`; `just test-browser` | PASS: Go, статический анализ, 147 UI tests, tooling, launcher и все browser E2E. |
