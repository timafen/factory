# CARD-0093 — санитар пропускает online/unhealthy Claude

Implementation commit: 9d80a5b829cbed76c40d8350d251011f77c36671 — опубликована проверяемая спецификация перед реализацией.

- Status: Specification — ожидает Implement + Test.
- Specification: `knowledge/specs/claude-janitor-does-not-restart-unhealthy-workers.md`.
- Scope: убрать холостые stop/start online/unhealthy и сохранить очистку offline retained.
- Required check: `bash ops/test-factory-janitor.sh`.
