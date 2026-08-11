Implementation commit: 3a5e2c9eed02f61b8aaa30a3a836af2b91c32634 — release fixture installs the privileged broker in a sandbox

# CARD-0064 — Release fixture includes the privileged broker

## HEAD

- Status: verified, ready to merge.
- Branch: `factory/release-fixture-complete`.
- Implementation commit: `3a5e2c9eed02f61b8aaa30a3a836af2b91c32634` — the end-to-end release fixture now carries and installs the broker artifacts without touching the host.
- Evidence: `bash ops/test-fx-factory-release.sh`, `bash ops/test-install-project-release-broker.sh`, `bash -n`, and `git diff --check` passed on the release host.
- One next action: merge and repeat the normal Factory release.

## LOG

### 2026-08-11 — Implement

The release fixture previously cloned only the older deployment files, so the production gate stopped before deployment when the new broker installer was absent. The fixture now copies the installer and unit, routes every broker installation target and system command into a temporary sandbox, and verifies the dedicated group, service unit, server supplementary-group drop-in, and broker binary.
