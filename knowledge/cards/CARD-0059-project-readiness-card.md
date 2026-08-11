# CARD-0059 — Полная карточка готовности нового проекта

## HEAD

Implementation commit: e1d50162290f72b3156503a40b0476a36b94df15 — реализована полная карточка готовности проекта из девяти безопасных проверок.

- Status: IMPLEMENTED — реализация и обязательная составная проверка завершены.
- Branch: `factory/e810f198-b10-8f930792-64b`.
- Specification: `knowledge/specs/project-readiness-card.md`.
- What changed: пилот публикует девять упорядоченных проверок, а «Обзор»
  показывает итог, причины и время снимка для каждого enabled-проекта.
- Evidence: обязательная Python + Go + Vitest + Playwright + shell-команда —
  PASS; `npm --prefix web run build` и lint — PASS.
- Safe defaults: unknown не становится ready, production-write не требуется,
  rollback не запускается, значения секретов и сырой stderr не публикуются.
- Next action: выбрать отдельный безопасный стенд для Factory либо оставить
  эту проверку в честном состоянии unknown.

## LOG

### 2026-08-10 — Specification

Зафиксированы существующие источники: каталог/маршрутизация репозиториев в
control plane, провайдерные `fx` probes, политика доступов, release-events и
установочный Chromium smoke. Для отсутствующих durable фактов о Verify и
браузере спецификация требует минимальные allowlisted markers вместо чтения
свободных логов или запуска опасных действий.

### 2026-08-10 — Implement

Реализован снимок готовности из девяти источников, строгая нормализация итогов
в UI и атомарный browser marker после успешного sandbox smoke. Обязательная
составная проверка прошла: 165 Python-тестов, целевые Go-тесты, 20 Vitest,
Playwright-карточка и установочный shell smoke; web build и lint также прошли.
