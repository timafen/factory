# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Implemented — готово к выкладке на staging.
- Branch: `factory/95307b86-884-5800b74d-8ff`.
- Head commit: `8ebc754` — владелец сам подтверждает доступ eBay в песочнице.
- What changed: добавлены `/sandbox-keys`, серверные start/status endpoints и
  строгий staging-only seller bridge. Экран открывает consent URL только по
  клику, опрашивает безопасный статус и не получает OAuth-поля.
- Evidence: `bash ops/fx_sandbox_test.sh`, `go test ./internal/controlplane`,
  `npx vitest run src/SandboxKeys.test.tsx src/App.test.tsx`, TypeScript и web
  build — успешно (7 новых UI-проверок плюс маршрут в App).
- One next action: выкатить Factory и `fx` на staging, пройти consent тестовым seller.

## LOG

### 2026-08-09 — Specification

Проверен код Factory. `ops/fx` уже вызывает staging Django-команду
`bootstrap_sandbox_accounts`, но его allowlist не принимает обязательные
`--interactive-bootstrap --role seller`. Factory не содержит кода eBay, callback
или encrypted token store. Спецификация
`knowledge/specs/sandbox-ebay-owner-consent.md` задаёт минимальную связку:
staging-only allowlist, server-side прокси фиксированной операции, отдельный
экран и polling безопасного статуса. Точный callback/API намеренно оставлен
зависимостью торгового репозитория, чтобы не переносить OAuth в Factory.

### 2026-08-09 — Implement

На ветке `factory/0f6cde34-11f-6563214b-b6d` добавлены экран ключей песочницы,
узкие server start/status endpoints и allowlist только для интерактивного seller
bootstrap на staging. Сервер передаёт UI только operation ID, consent URL, status
и безопасное сообщение; OAuth code, state и токены отсекаются. Проверены
`go test ./internal/controlplane`, `npx vitest run src/SandboxKeys.test.tsx src/App.test.tsx`
и `npx tsc -p tsconfig.app.json --noEmit`.

### 2026-08-09 — Implement

На ветке `factory/cb28ad85-83b-1bb9646b-b94` исправлена зависающая проверка
polling и добавлены сценарии отказа с повторным запуском, остановки polling при
уходе и прямого маршрута `/sandbox-keys`. Целевые 66 Vitest-проверок, Go,
TypeScript, build и lint прошли. Полный Vitest выявил только три прежних сбоя
`Dialog.test.tsx`, не изменённого поставкой; live smoke требует сначала выкатить
новый `fx`.

### 2026-08-09 — Implement

По решению владельца три сбоя полного Vitest воспроизведены на отдельном чистом
снимке свежего `origin/main`: падают ровно те же три теста `Dialog.test.tsx`
(main 98/101, ветка 103/106). Целевые UI-тесты прошли 66/66, отдельная правильная
проверка `npx tsc -p tsconfig.app.json --noEmit`, build, lint и Go-проверки
прошли. Живой smoke остаётся обязательным после обновления `fx` и выката main.

### 2026-08-09 — Implement

По решению владельца реализация из `22a296f` перенесена заново на свежий
`origin/main` без посторонних файлов. Экран, server endpoints, строгий
staging-only seller bridge и тесты закреплены коммитом `dedd492`. Прошли Go,
TypeScript, build, lint и 69/69 целевых UI-тестов; полный Vitest сохранил три
известных сбоя `Dialog.test.tsx`, не затронутого поставкой.

### 2026-08-09 — Implement

На свежем `origin/main` восстановлены server endpoints, экран `/sandbox-keys`,
маршрут и фиксированный staging-only seller bridge. Добавлена отдельная
проверка `ops/fx_sandbox_test.sh`: она подтверждает точный запуск seller и
status path, а также отклонение другой роли, лишних флагов и смешанных команд.
Целевые Go и Vitest проверки, TypeScript и web build прошли успешно.
