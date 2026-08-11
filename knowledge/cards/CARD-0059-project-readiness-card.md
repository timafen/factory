Implementation commit: 1f5cb6ef16ef17481acf2ef8f00b4ce5f1e720a9 — пилот собирает девять проверок готовности, а «Обзор» показывает их итог и причины.

# CARD-0059 — Полная карточка готовности нового проекта

## HEAD

- Status: IMPLEMENTED — реализация и повторная проверка завершены.
- Branch: `factory/adffe344-c2e-6dd68514-c2a`.
- Implementation commit: `1f5cb6ef16ef17481acf2ef8f00b4ce5f1e720a9` —
  полный снимок готовности и карточка на «Обзоре».
- Specification: `knowledge/specs/project-readiness-card.md`.
- What changed: пилот собирает девять безопасных проверок для каждого
  включённого проекта; «Обзор» показывает итог, причины и время снимка.
- Safe defaults: неизвестное не считается готовностью; production-write не
  включается и не требуется; секреты не покидают источник в виде значений.
- Evidence: `python3 -m unittest pilot.test_pilot` — 165 passed;
  целевой Go — passed; Overview Vitest — 20 passed; Playwright — 1 passed;
  browser installer smoke — passed; обязательный `tsc --noEmit` — passed;
  `just check` — passed, включая полный Go и 140 UI-тестов.
- Next action: открыть `/` после выкладки и проверить карточку проекта глазами.

## LOG

### 2026-08-10 — Specification

Зафиксированы существующие источники: каталог/маршрутизация репозиториев в
control plane, провайдерные `fx` probes, политика доступов, release-events и
установочный Chromium smoke. Для отсутствующих durable фактов о Verify и
браузере спецификация требует минимальные allowlisted markers вместо чтения
свободных логов или запуска опасных действий.

### 2026-08-10 — Implement

Реализованы девять фиксированных проверок готовности, безопасные provider-probes,
browser marker и детерминированный итог на экране «Обзор». Повторная проверка:
165 pilot-тестов, целевой Go, 20 Overview-тестов, browser installer smoke,
обязательный `tsc --noEmit`, Playwright-сценарий и полный `just check` прошли.
