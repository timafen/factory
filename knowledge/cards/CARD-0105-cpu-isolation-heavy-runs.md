# CARD-0105 — Изоляция по процессору для тяжёлых прогонов

Implementation commit: c07bb2ff7362a1a0057cf19232ffb46beebf5b6f — CPU-допуск резервирует тяжёлые прогоны по уникальному `work_id`

## HEAD

- Status: Implement + Test завершён; базовые сбои подтверждены на свежем `origin/main`; готово к Review.
- Branch: `factory/e0fd21ab-0d5-e105c96a-7b5`.
- Implementation commit: `c07bb2ff7362a1a0057cf19232ffb46beebf5b6f`.
- What changed: продолжения одной работы делят CPU-резерв, одноимённые работы с разными `work_id` остаются независимыми; завершение освобождает резерв на свежем снимке.
- Evidence: CPU admission 13/13, Overview 28/28, полный web-набор 172/172 и ESLint прошли; полный Python-набор: 248/250, два подтверждённых базовых сбоя.
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

### 2026-08-12 — Verify

- Свежий `origin/main` зафиксирован как `c28b5bfc0c5bbb22c7d69d0749c316a2b340841e`; независимый снимок воспроизводит два `FAIL` в `CorrectionProvenanceStormTests.test_review_and_verify_corrections_complete_one_pipeline_after_restart` (`review_return`, `verify_return`) и `TS2339` в `web/e2e/control-plane.spec.ts:655` (`Navigator.serviceWorker`).
- На ветке CARD-0105: `HostLoadAdmissionTests` — 13/13 PASS; `Overview.test.ts` — 28/28 PASS; полный web-набор — 172/172 PASS; ESLint — PASS. Полный `pilot.test_pilot` даёт 248 PASS, 2 тех же базовых FAIL, 13 skipped; `npm run build` даёт ту же базовую `TS2339`.
- Чистая область `git diff --name-only origin/main...HEAD`: `knowledge/cards/CARD-0105-cpu-isolation-heavy-runs.md`, `knowledge/specs/cpu-isolation-heavy-runs.md`, `pilot/pilot.py`, `pilot/test_pilot.py`.
