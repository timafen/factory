# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Implemented — реализация восстановлена на свежем `origin/main`.
- Branch: `factory/3d1f8660-a24-adb8dd5d-a3f`.
- Head commit: `32bb42a` — полный проверяемый путь согласия eBay.
- What changed: добавлены `/sandbox-keys`, серверные start/status endpoints и
  строгий staging-only seller bridge. UI открывает consent URL только по клику
  и опрашивает безопасный статус; OAuth-поля отбрасываются на сервере.
- Evidence: `go test ./internal/controlplane` и целевой Vitest 69/69 — успешно;
  `npx tsc -p tsconfig.app.json --noEmit`, web build, lint и `bash -n ops/fx`
  — успешно.
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

По решению владельца реализация из `22a296f` перенесена заново на свежий
`origin/main` без посторонних файлов. Экран, server endpoints, строгий
staging-only seller bridge и тесты закреплены коммитом `dedd492`. Прошли Go,
TypeScript, build, lint и 69/69 целевых UI-тестов; полный Vitest сохранил три
известных сбоя `Dialog.test.tsx`, не затронутого поставкой.

### 2026-08-09 — Implement

По решению владельца реализация и тесты восстановлены на чистой ветке от
свежего `origin/main` коммитом `32bb42a`, без файлов прежней грязной ветки.
Прошли `go test ./internal/controlplane`, 69/69 целевых UI-тестов, TypeScript,
production build, lint и синтаксическая проверка `ops/fx`.
