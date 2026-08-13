# CARD-0105 — Изоляция по процессору для тяжёлых прогонов

Implementation commit: c07bb2ff7362a1a0057cf19232ffb46beebf5b6f — CPU-допуск резервирует тяжёлые прогоны по уникальному `work_id`

## HEAD

- Status: Implement + Test завершён; готово к Review.
- Branch: `factory/5e40a9ea-eeb-ee1401ae-fa8`.
- Implementation commit: `c07bb2ff7362a1a0057cf19232ffb46beebf5b6f`.
- What changed: продолжения одной работы делят CPU-резерв, одноимённые работы с разными `work_id` остаются независимыми; завершение освобождает резерв на свежем снимке.
- Evidence: `python3 -m unittest pilot.test_pilot.HostLoadAdmissionTests` → 13 passed; `npm test -- --run src/Overview.test.ts` → 28 passed; `npm run lint` → passed.
- Next action: Review проверяет diff относительно свежего default branch.

## LOG

### 2026-08-12 — Specification

- Зафиксирован контракт мягкого CPU-допуска, сохранения доступности панели и Brain, диагностики активных работ и исполнительских слотов.
- Полная спецификация: `knowledge/specs/cpu-isolation-heavy-runs.md`.

### 2026-08-12 — Implement

- Резерв тяжёлого запуска переведён с количества строк задач на уникальные `work_id`; новый запуск резервируется сразу после ответа API.
- Целевые проверки: 13 Python-тестов и 28 UI-тестов прошли, lint прошёл.
- Общий Python-набор: 248 из 250 прошли, 13 skipped; два существующих сбоя `CorrectionProvenanceStormTests` вне области изменения.
- Web build заблокирован существующей ошибкой типов в `web/e2e/control-plane.spec.ts:655`, вне области CARD-0105.
