Implementation commit: 714e6b7b8a394414eff574e8ef4d8dc4e36b5a76 — explicit worker config does not require a home directory

# CARD-0066 — Explicit worker config works without HOME

## HEAD

- Status: verified, ready to merge.
- Branch: `factory/worker-explicit-config`.
- Implementation commit: `714e6b7b8a394414eff574e8ef4d8dc4e36b5a76` — worker subcommands skip home-directory discovery when a config path is supplied explicitly.
- Evidence: worker command tests pass; the production config returns the existing worker identity with `HOME` and every Factory config environment variable unset; the complete release scenario and `git diff --check` pass.
- One next action: merge and repeat the normal release.

## LOG

### 2026-08-11 — Implement

The release runs as an isolated transient service without `HOME`. Although it supplied `-config`, the worker resolved the unused default path before parsing that flag and failed. Explicit `-config` and `--config` forms are now detected before default discovery, including cleanup subcommands.
