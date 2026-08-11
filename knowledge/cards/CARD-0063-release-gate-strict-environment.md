Implementation commit: 91921edd4fa557f09c88fa1c462129562d82efef ? deterministic release gate and isolated privileged broker

# CARD-0063 ? Release gate matches the production environment

## HEAD

- Status: verified, ready to merge.
- Branch: `factory/release-gate-strict-env`.
- Implementation commit: `91921edd4fa557f09c88fa1c462129562d82efef` ? fixtures are umask-independent, duplicate Git probes wait safely, and only the control plane can reach the privileged broker.
- Evidence: strict-umask targeted tests passed; the former repository race passed 20 consecutive runs; `go test ./...` passed; broker installer test and `git diff --check` passed.
- One next action: merge and repeat the normal Factory release.

## LOG

### 2026-08-11 ? Implement

The production release gate exposed test fixtures whose requested modes were silently narrowed by `umask 077`; the fixtures now set their intended modes explicitly. Transient duplicate Git probes wait for the existing probe instead of failing unrelated repository acquisition. The root-owned release broker now uses a dedicated supplementary group unavailable to workers, its installer provisions the server drop-in, and an updated broker is restarted.
