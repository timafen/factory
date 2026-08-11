# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/be36087a-432-729507f1-249`.
Implementation commit: bdd3043235fdbbc72e4c794c960f68609f69ad20 — План, Уведомления и подписи интерфейса приведены к единому русскому виду.
- What changed: реальные `/plan` и `/alerts` получили компактные disclosures и группы; control plane получил русский словарь и точечную адаптивную компоновку.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 5 tests, OK; `npm test` → 147 tests, PASS; целевые Playwright-аудиты → PASS на desktop и phone.
- Next action: Verify запускает полный browser suite.

## LOG

### 2026-08-11 — Implement

Добавлены реальные router-backed browser-проверки Плана и Уведомлений со
снимками для 1440 px и 390 px. План скрывает обоснование до раскрытия, а
Уведомления показывают до 30 свежих событий в сворачиваемых группах. Русские
labels и responsive-правила проверены Vitest, Playwright, lint, typecheck,
сборкой и `go test ./...`; полный browser suite оставлен этапу Verify.
