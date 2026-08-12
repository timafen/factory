# CARD-0090 — Автовыпуск подтверждает перезапуск сервера и воркеров

Implementation commit: add62d7db9829b58538336be9dedd86d7e7ea620 — существующая база выпуска управляет всеми заданными worker-службами; данная карточка определяет следующую проверку фактической смены процессов.

## HEAD

- Status: Specification ready for Implement.
- Branch: `factory/dcc68b3d-95e-46a2ad06-104`.
- Specification: `knowledge/specs/auto-release-restarts-server-workers.md`.
- Scope: `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`, `ops/test-factory-release-systemd.sh`.
- Mandatory evidence: `bash ops/test-fx-factory-release.sh` exits 0 and covers a new server plus every active configured worker process.

## LOG

### 2026-08-12 — Specification

The incident report says that an automatic release replaced binaries at 19:03:40
CDT without proving that `factory-server` and workers were restarted. Current
code stops workers and server, installs a generation, starts them again and
checks executable hashes, but the fixture only observes lifecycle commands.
The next implementation must make successful release contingent on a changed
process identity and manifest-matching executable for every initially active
server/worker unit, with full rollback on failure. No production action is
authorized by this specification.
