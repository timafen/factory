Implementation commit: b7680d83f05a7311b912c437306e3df6189ca3fb — тест закрепляет перезапуск активного release broker

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: implemented and verified.
- Branch: `factory/ba0e4ca8-bf6-435aed8c-2f3`.
- Implementation commit: `b7680d83f05a7311b912c437306e3df6189ca3fb` — installer test covers the active service path after binary replacement.
- What changed: the installer regression test now simulates an active broker and requires `daemon-reload` plus exactly one service restart, without enabling it again.
- Evidence: `bash ops/test-install-project-release-broker.sh` passed; both inactive and active service paths completed successfully.
- One next action: merge the regression test with the release-broker installer changes.

## LOG

### 2026-08-11 — Implement

The installer already restarted an active `factory-release-broker.service`, but its test covered only the inactive-service branch. The new scenario makes `systemctl is-active --quiet` succeed and verifies one `restart factory-release-broker.service`, `daemon-reload`, and the absence of `enable --now`; the previous inactive branch remains covered. Verified with `bash ops/test-install-project-release-broker.sh`.
