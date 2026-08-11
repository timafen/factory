Implementation commit: f44edca341b27a8033bd2ebdf650b93945153aab — повторная установка проверяет замену бинаря и перезапуск активного release-broker

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: verified, ready for Review.
- Branch: `factory/a1e4ebce-ff2-a5a6bbb7-88d`.
- Implementation commit: `f44edca341b27a8033bd2ebdf650b93945153aab` — тест повторной установки подтверждает замену бинаря до перезапуска активного сервиса.
- What changed: installer regression coverage now exercises both the first installation and an update of an already active `factory-release-broker`.
- Evidence: `just test-tooling` passes both installation paths; `just build` produces the broker binary; `git diff --check` passes.
- One next action: repeat Review on the published branch before any rollout.

## LOG

### 2026-08-11 — Implement

Added a second installer run with a new binary and an active-service response. The systemctl test double verifies that version 2 is already installed when `restart factory-release-broker.service` runs and rejects an `enable --now` fallback for that path.
