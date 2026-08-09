# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Implemented — проверки поставки зелёные, ждёт выката и smoke на staging.
- Branch: `factory/6f8b4c51-051-e01a5ac4-e4e`.
- Head commit: `43dd054` — закреплён полный проверяемый путь согласия eBay.
- What changed: добавлены `/sandbox-keys`, серверные start/status endpoints и
  строгий staging-only seller bridge. UI открывает consent URL только по клику
  и опрашивает безопасный статус; OAuth-поля отбрасываются на сервере.
- Evidence: `go test ./internal/controlplane` и целевой Vitest 66/66 — успешно;
  `npx tsc -p tsconfig.app.json --noEmit`, web build и lint — успешно. Полный
  Vitest: те же 3 сбоя `Dialog.test.tsx` на свежем main (98/101) и ветке
  (103/106), поэтому это подтверждённый прежний дефект, а не регрессия поставки.
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
