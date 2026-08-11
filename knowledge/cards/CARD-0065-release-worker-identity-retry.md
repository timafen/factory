Implementation commit: 4c7cebdf5ecf80a370c6e6da4974b80a381b2623 — release retries transient worker identity acquisition

# CARD-0065 — Release waits for worker identity

## HEAD

- Status: verified, ready to merge.
- Branch: `factory/release-identity-retry`.
- Implementation commit: `4c7cebdf5ecf80a370c6e6da4974b80a381b2623` — a transient data-directory lock no longer forces an immediate rollback, and a persistent failure keeps a bounded diagnostic.
- Evidence: the complete release scenario passes, including a new first-attempt identity failure followed by a successful retry; shell syntax and `git diff --check` pass.
- One next action: merge, bootstrap the installed release driver from trusted main, and repeat the release.

## LOG

### 2026-08-11 — Implement

The production release passed every code and UI gate but rolled back when the replacement worker could not acquire its identity on the first instant after service stop. The release now retries the bounded operation five times and reports a short underlying reason if the lock never clears.
