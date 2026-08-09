# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Implemented — блокирующие замечания устранены, ждёт повторной проверки.
- Branch: `factory/1066fc78-dd8-5ac74721-5be`.
- Head commit: `22a296f` — реализация безопасного status API и polling.
- What changed: status API сверяет operation ID и выдаёт отдельную модель без
  URL/секретов. UI хранит проверенную ссылку старта отдельно, опрашивает статус
  последовательно и не откатывается из конечного состояния.
- Evidence: `go test ./...` — успешно; целевой Vitest 69/69, TypeScript, build
  и lint — успешно. Полный Vitest: прежние 3 сбоя `Dialog.test.tsx`, 106/109.
- One next action: выкатить Factory на staging и пройти eBay consent тестовым seller.

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

На ветке `factory/1066fc78-dd8-5ac74721-5be` закрыто блокирующее замечание
ревью: status API теперь сверяет operation ID и не способен вернуть подменённый
URL или секретные поля. UI сохраняет ссылку только из start-ответа, polling
последовательный и защищён от регресса `authorized` в `pending`. Целевые Vitest
69/69, полный Go, TypeScript, build и lint прошли; полный Vitest сохранил три
известных сбоя `Dialog.test.tsx` (106/109).
