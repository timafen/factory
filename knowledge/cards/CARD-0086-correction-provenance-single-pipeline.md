# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and tested; Pilot remains operationally disabled.
- Branch: `factory/09c06928-01c-3635241e-3e3`.
- Implementation commit: 39606ecb8889f5a7df5d7822e6d9c28f497d4c09 — provenance и состояния возобновления изолируют корректировки по устойчивому `work_id`.
- What changed: задачи хранят `work_id`, родительскую задачу и вид корректировки; Pilot использует эту provenance, чтобы не запускать второй корень.
- What changed: одноимённые работы, их возобновления, бюджет и диагностика изолированы; legacy-задачи остаются совместимы.
- Evidence: `go test ./...`, `go build ./...`, `python3 -m unittest pilot.test_pilot -q` and `npx tsc -p tsconfig.app.json --noEmit` → PASS.
- Next action: review and merge; keep Pilot disabled pending its separate release decision.

## LOG

### 2026-08-12 — Implement

On fresh `origin/main` `07491cc7b26bbc47dca9f8fd5109f2c665f1fa53`, added migration 027 and durable task provenance. Pilot now groups correction stages by `work_id`, persists the prevented-root event across restart, and keeps same-title work and owner resume independent. Focused Control Plane tests, the full Go suite/build, all Pilot tests, and the required web TypeScript check passed.
