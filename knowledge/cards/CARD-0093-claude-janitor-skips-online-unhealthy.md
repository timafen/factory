# CARD-0093 — санитар пропускает online/unhealthy Claude

Implementation commit: pending — реализация будет выполнена на следующем этапе после этой спецификации.

- Status: Specification — ожидает Implement + Test.
- Specification: `knowledge/specs/claude-janitor-does-not-restart-unhealthy-workers.md`.
- Scope: убрать холостые stop/start online/unhealthy и сохранить очистку offline retained.
- Required check: `bash ops/test-factory-janitor.sh`.
