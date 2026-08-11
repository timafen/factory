# CARD-0068 — Полный визуальный аудит Factory на компьютере и телефоне

Implementation commit: da8fd02a1724fee373970c44ee8cfee98c29c075 — аудит выявляет выходящие и обрезанные интерактивные элементы

## HEAD

- Status: Implemented, rebased and browser-verified
- Branch: `factory/294beb15-1ec-b4eba6f8-024`
- Implementation commit: `da8fd02a1724fee373970c44ee8cfee98c29c075`
- What changed: полный аудит всех экранов теперь разрешает исключения только для
  явных horizontal scrollers и проверяет их границы. Overflow и обрезание
  интерактивных элементов, включая нативные `main button`, стали assertions.
- Evidence: целевой Playwright-аудит после rebase — 1 passed (2.1m); production
  build, отдельный typecheck и `git diff --check` завершились с exit code 0.
- Next action: Verify подтверждает поставку на опубликованной ветке.

## LOG

### 2026-08-11 — Specification

Область ограничена двумя файлами: существующий browser suite становится полным
и самодостаточным, а визуальные исправления остаются в общем stylesheet. Новых
API и pixel snapshots нет. Контракт и проверяемые обещания записаны в
`knowledge/specs/full-visual-audit-desktop-mobile.md`.

### 2026-08-11 — Implement

Добавлен аудит всех 22 React-состояний в desktop/phone и 44 именованных снимка.
По его результатам исправлены мобильные меню, метрики Overview, готовность проекта
и Settings; sticky-действие больше не перекрывает поля. Целевой Playwright-тест
завершился `1 passed (1.9m)`, production build/typecheck и diff-check зелёные.

### 2026-08-11 — Implement

После Review исключение из геометрической проверки сужено до явных контейнеров
`overflow-x: auto/scroll`; их собственные границы теперь тоже проверяются.
Добавлены обязательные assertions для найденного overflow и регрессия с нативными
`main button`. После rebase целевой аудит дал `1 passed (2.1m)`; build, typecheck
и `git diff --check` завершились успешно.
