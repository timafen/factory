## HEAD

Status: implemented
Branch: factory/740d296f-fdc-d982ce63-818
Head commit: b492b70
What changed: UI tests now find the renamed main screen («Главное»), workflow navigation, and current history action labels.
Evidence: `npx vitest run src/App.test.tsx -t 'renamed main screen|marks only exact navigation|creates, revises' --reporter=verbose` → 3 passed.
Next action: run the full web test suite in CI; unrelated legacy expectations in `App.test.tsx` still need their own task.

## LOG

### 2026-08-08 — Implement

Updated `web/src/App.test.tsx` to use the current screen labels and removed stale overview-metrics checks from the renamed main screen test. Targeted UI tests passed; full-suite baseline includes unrelated stale assertions outside this card's scope.
