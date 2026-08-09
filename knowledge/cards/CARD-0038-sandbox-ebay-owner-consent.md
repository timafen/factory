# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Implemented — ждёт выката Factory и smoke на staging.
- Branch: `factory/0f6cde34-11f-6563214b-b6d`.
- Head commit: `2988dc6` — владелец сам подтверждает eBay продавца в песочнице.
- What changed: добавлены `/sandbox-keys`, серверные start/status endpoints и
  строгий staging-only seller bridge. UI открывает consent URL только по клику
  и опрашивает безопасный статус; OAuth-поля отбрасываются на сервере.
- Evidence: `go test ./internal/controlplane`, Vitest и `tsc --noEmit` — успешно.
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
