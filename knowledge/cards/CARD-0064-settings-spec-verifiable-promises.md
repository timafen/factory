# Проверяемые обещания спецификации экрана «Настройки»

Implementation commit: 81da8e1af04b24c365fdcd1d0cb2da689dd819d3 — экран объясняет конфликт версии, а тесты подтверждают безопасную запись настроек.

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/2f0f0d19-637-98a58881-590`.
- What changed: конфликт версии предлагает владельцу загрузить свежие настройки;
  тесты закрепляют порядок моделей, атомарную замену и сохранность прежнего файла.
- Evidence: `go test ./internal/controlplane -count=1` → PASS;
  `npm --prefix web test -- --run --reporter=dot` → 146 PASS;
  web lint и production build → PASS.
- One next action: проверить экран `/settings` и влить поставку в `main`.

## Границы

- Реализация экрана и API уже была в `main`; поставка добавляет недостающие
  подтверждения критериев и локализует действие при конфликте версии.

## LOG

### 2026-08-11 — Implement

Отдельная поставка подтвердила атомарную замену файла, сохранность прежних байтов
при сбое, безопасные ошибки missing/oversized/invalid, перестановку `brain_chain`
с notes и восстановление после `409`. Полный пакет control-plane, 146 web-тестов,
lint и production build прошли.

### 2026-08-11 — Specification

Спецификация `docs/software-factory/settings-spec.md` дополнена списком файлов
реализации и воспроизводимой целевой командой проверки. Обещания связали экран
`/settings`, API и атомарное хранение настроек с проверяемым результатом.
