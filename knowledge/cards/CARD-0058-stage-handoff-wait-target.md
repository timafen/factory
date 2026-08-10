Implementation commit: 9b7ad916ab1cfb8665bce395a14ac26887667db7 — Обзор показывает достижение цели ожидания между стадиями

# CARD-0058 — Цель ожидания между стадиями

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/35e7811c-d36-9e9232b3-41c`.
- Implementation commit: 9b7ad916ab1cfb8665bce395a14ac26887667db7 — Обзор показывает достижение цели ожидания между стадиями.
- What changed: API сравнивает недельную долю ожидания передачи стадии с целью ≤10%; Обзор показывает текущую, предыдущую долю и честный статус.
- Evidence: `go test ./internal/controlplane -run 'TestEfficiency(UsesMergedProductWorkAndHonestDenominators|TargetComparesCurrentAndPreviousStageHandoffShares)' -count=1` → PASS; `npm --prefix web test -- --run src/Overview.test.ts` → 14 passed; `npm --prefix web run build` → PASS.
- One next action: проверить на стенде недельную метрику после накопления достаточных данных.

## LOG

### 2026-08-10 — Implement

Добавлена проверяемая цель: ожидание между стадиями должно занимать не более 10% lead time за семь дней. Если фактов недостаточно, API и экран не заявляют о достижении; иначе показываются текущая и предыдущая доли. Целевые Go- и UI-тесты, а также production-сборка прошли.
