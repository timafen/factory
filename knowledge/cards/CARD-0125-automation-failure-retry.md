Implementation commit: ebf463fd7931774c1f80457f27badd970512a040 — панель Automation показывает состояние автоматического повтора и окончательного сбоя.

## HEAD

Status: implemented
Branch: factory/e68ace28-60a-d53f4bba-34b
Implementation commit: ebf463fd7931774c1f80457f27badd970512a040 — панель Automation показывает состояние автоматического повтора и окончательного сбоя.
What changed: Automation API проецирует retry count/status; экран показывает русские метки очереди, выполнения, окончательного сбоя и причин запрета повтора.
Evidence: `go test ./...` → PASS; `npm run build` (web) → PASS; 5 целевых UI-сценариев → PASS.
Next action: открыть Automation на стенде и подтвердить метки на реальном запуске.

## LOG

### 2026-08-13 — Implement

Added a durable one-time retry for failed scheduled and Run now Automation executions, including lease-expiry failures. The focused lifecycle/idempotency test and Automation/Schedule regression suite pass.

### 2026-08-13 — Implement

Added owner-facing `retry_status` projection and Russian Automation run labels for queued/running retry, final failure, disabled Automation, and unavailable worker. Full Go tests and web production build pass; focused UI scenarios pass.
