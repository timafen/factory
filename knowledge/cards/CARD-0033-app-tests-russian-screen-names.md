## HEAD

Status: implemented
Branch: factory/ae513996-ccb-428c2f43-87e
Head commit: 625e8c4
What changed: UI tests now find the renamed main screen («Главное»), workflow navigation, and current history action labels.
Evidence: targeted Vitest → 3 passed; `npm run build` → passed.
Next action: update the remaining 12 stale `App.test.tsx` scenarios in a separate small batch.

## LOG

### 2026-08-08 — Implement

Updated `web/src/App.test.tsx` to use the current screen labels and removed stale overview-metrics checks from the renamed main screen test. Targeted UI tests passed; full-suite baseline includes unrelated stale assertions outside this card's scope.

### 2026-08-08 — Implement

Delivered the smallest verified batch on `factory/ae513996-ccb-428c2f43-87e`: renamed main navigation, Workflow navigation, and task-history labels. The three targeted scenarios pass and the web production build succeeds. The full file still has 12 unrelated stale scenarios; lint also retains pre-existing errors outside this card's diff.
