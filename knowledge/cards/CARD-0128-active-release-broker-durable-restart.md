# CARD-0128 — Active release broker: durable restart

Implementation commit: 6115354d94aca6d67a91b9bc32facc6af7c01b25 — installer надёжно фиксирует замену broker до systemd restart

## HEAD

- Status: Implemented — ожидает Verify.
- Branch: `factory/2ca7ec7a-536-0ce0c8a8-329`.
- Implementation commit: `6115354d94aca6d67a91b9bc32facc6af7c01b25` — installer синхронизирует кандидатные файлы до rename и каталоги после него.
- What changed: active `factory-release-broker.service` остаётся на ветке `restart`, inactive — на `enable --now`; Pilot перезапускается после broker.
- Evidence: `go test ./internal/releasebroker ./cmd/factory-release-broker`, `bash ops/test-install-project-release-broker.sh`, `bash ops/test-fx-factory-release.sh`, `bash -n` и `git diff --check` — PASS.
- Next action: Verify должен подтвердить полный набор и staging systemd smoke на разрешённом хосте.

## LOG

### 2026-08-14 — Implement

Установщик сохраняет candidate broker/unit/drop-in в sibling-файлы, выполняет fsync до атомарной замены и fsync каталогов после неё. Fixture подтверждает обе точки синхронизации, установленную новую версию до restart и раздельные active/inactive ветки systemd. Целевые Go, installer и release-driver проверки прошли.
