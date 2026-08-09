## HEAD

Status: implemented
Branch: factory/71ef32c4-d70-b90c7342-c0d
Head commit: 4227ee8
What changed: all 58 `App.test.tsx` scenarios now exercise the current labels, request limits, grouped work view, and expandable task details; no skipped checks remain.
Two managed-repository delegation checks were removed because that picker now lists only repositories advertised by the selected worker and no longer offers managed routing-on-demand.
Evidence: `npm test -- --run src/App.test.tsx` → 58 passed; `npm run build` → passed; full web Vitest → 91 passed, 1 unrelated `Settings.test.tsx` failure.
Next action: verify the focused UI test file on the delivery branch.

## LOG

### 2026-08-08 — Implement

Finished the stale-scenario audit on `factory/71ef32c4-d70-b90c7342-c0d`. Rewrote ten still-valid checks for the 200-item API pages, Russian stage-board labels, and collapsed task prompt sections. Removed two checks for managed repositories and routing-on-demand because the current delegate dialog exposes only repositories advertised by its selected worker. The focused file passes all 58 tests with no skips and the production build succeeds; the full web suite retains one unrelated failure in `Settings.test.tsx`.

### 2026-08-08 — Implement

Updated `web/src/App.test.tsx` to use the current screen labels and removed stale overview-metrics checks from the renamed main screen test. Targeted UI tests passed; full-suite baseline includes unrelated stale assertions outside this card's scope.

### 2026-08-08 — Implement

Delivered the smallest verified batch on `factory/ae513996-ccb-428c2f43-87e`: renamed main navigation, Workflow navigation, and task-history labels. The three targeted scenarios pass and the web production build succeeds. The full file still has 12 unrelated stale scenarios; lint also retains pre-existing errors outside this card's diff.
