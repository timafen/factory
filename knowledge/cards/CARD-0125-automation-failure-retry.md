Implementation commit: b9faec584be7c3420f5b0f114b3b8230b2278941 — провалившийся schedule Automation один раз возвращается в очередь.

## HEAD

Status: implemented
Branch: factory/9fedd387-3d5-d17b5640-5fe
Implementation commit: b9faec584be7c3420f5b0f114b3b8230b2278941 — провалившийся schedule Automation один раз возвращается в очередь.
What changed: terminal failure and expired lease share an atomic, eligibility-checked retry transition; second failure stays final.
Evidence: `go test ./internal/controlplane -run 'Test.*(Automation|Schedule)' -count=1` → PASS.
Next action: review the owner-facing retry status projection and UI labels from the specification.

## LOG

### 2026-08-13 — Implement

Added a durable one-time retry for failed scheduled and Run now Automation executions, including lease-expiry failures. The focused lifecycle/idempotency test and Automation/Schedule regression suite pass.
