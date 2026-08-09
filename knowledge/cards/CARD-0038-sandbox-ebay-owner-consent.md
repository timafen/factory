# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Blocked — в `tarser-operations` нет безопасного start/status-контракта
  для Factory.
- Branch: `factory/802cfd44-f99-d37f5434-47d`.
- Head commit: `bc098ed`.
- What changed: подтверждён callback
  `/marketplaces/ebay/oauth/callback/`; реализация Factory остановлена до
  появления структурированных start/status операций в торговой системе.
- Boundary: production, OAuth-код, access/refresh tokens и client secrets не
  попадают в Factory.
- Evidence: `tarser-operations@6f6e286` содержит session-bound begin/callback;
  `bootstrap_sandbox_accounts` ждёт redirect URL через `input()`, status API
  отсутствует; staging объявляет точное имя callback-настройки.
- One next action: реализовать и выпустить в `tarser-operations` staging-only
  start/status-контракт без OAuth-кода и токенов в ответах.

## LOG

### 2026-08-09 — Implement

Проверен актуальный `tarser-operations@6f6e286` и доступный staging-контракт.
Публичный путь callback существует, но `ebay_oauth_begin` и callback привязаны
к Django-сессии, CLI интерактивно принимает полный redirect URL, а отдельной
операции и безопасного статуса для polling нет. По утверждённой границе Factory
не может принимать OAuth-код или подменять торговую систему, поэтому изменения
`ops/fx`, server API и UI не начаты до устранения этой блокирующей зависимости.

### 2026-08-09 — Specification

Проверен код Factory. `ops/fx` уже вызывает staging Django-команду
`bootstrap_sandbox_accounts`, но его allowlist не принимает обязательные
`--interactive-bootstrap --role seller`. Factory не содержит кода eBay, callback
или encrypted token store. Спецификация
`knowledge/specs/sandbox-ebay-owner-consent.md` задаёт минимальную связку:
staging-only allowlist, server-side прокси фиксированной операции, отдельный
экран и polling безопасного статуса. Точный callback/API намеренно оставлен
зависимостью торгового репозитория, чтобы не переносить OAuth в Factory.
