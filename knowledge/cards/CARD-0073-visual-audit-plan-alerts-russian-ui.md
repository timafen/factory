# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/46c1169d-306-eeac2047-f6d`.
Implementation commit: 5442ad5450b3192c99fad32ca5394f2678eb7a59 — План сохраняет внешний `/intake/plan`, а TaskDetail, постановка задачи и общий словарь переведены.
- What changed: redirect `Location` нормализуется к публичному пути; технические ID/SHA остаются без изменений.
- What changed: intake и control-plane browser fixtures используют раздельные свободные порты после ребейза на `main`.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 5 OK; `npm test` → 156 PASS; `go test ./...` → PASS; целевые Playwright-аудиты → 2 + 1 PASS на 1440/390.
- Next action: Verify запускает полный browser suite.

## LOG

### 2026-08-11 — Implement

Добавлены реальные router-backed browser-проверки Плана и Уведомлений со
снимками для 1440 px и 390 px. План скрывает обоснование до раскрытия, а
Уведомления показывают до 30 свежих событий в сворачиваемых группах. Русские
labels и responsive-правила проверены Vitest, Playwright, lint, typecheck,
сборкой и `go test ./...`; полный browser suite оставлен этапу Verify.

### 2026-08-11 — Implement

Исправлены четыре замечания Review: внешний redirect Плана, русские TaskDetail
и DelegateModal, а также общий словарь состояния, обновления, ошибок и повторов.
Проверены `Location`, role/name selectors и сохранение ID/SHA; intake-аудит прошёл
на 1440/390, как и общий control-plane аудит. После ребейза intake fixture также
получил отдельный свободный порт; полный browser suite остаётся этапу Verify.
