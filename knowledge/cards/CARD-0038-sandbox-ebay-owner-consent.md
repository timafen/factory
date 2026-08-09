# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Specification ready — ждёт подтверждения зависимости
  `tarser-operations`.
- What changes: Factory начнёт только запускать staging seller consent, открывать
  ссылку eBay и показывать безопасный статус. Callback и зашифрованное хранение
  токена остаются у торговой системы.
- Boundary: production, OAuth-код, access/refresh tokens и client secrets не
  попадают в Factory.
- One next action: сначала проверить и при необходимости реализовать callback
  и безопасный контракт в `tarser-operations`, затем передать его Implement.

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
