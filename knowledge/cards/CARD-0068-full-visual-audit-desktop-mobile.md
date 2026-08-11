# CARD-0068 — Полный визуальный аудит Factory на компьютере и телефоне

Implementation commit: pending — будет записан Implement-стейджем после изменения кода

## HEAD

- Status: Specification ready for implementation
- Branch: `factory/f45a18da-41f-a7090c3d-0f6`
- What changes: все маршруты React-интерфейса, detail-экраны и окно постановки
  задачи получают воспроизводимый Playwright-аудит при 1440×1000 и 390×844;
  подтверждённые дефекты компоновки исправляются в общем responsive CSS.
- Evidence: фактическая карта маршрутов сверена с `web/src/App.tsx`, responsive
  правила — с `web/src/styles.css`, текущий неполный narrow smoke — с
  `web/e2e/control-plane.spec.ts` и `web/playwright.config.ts`.
- Next action: Implement добавляет целевой красный тест, исправляет найденные им
  layout-дефекты, записывает сюда полный SHA отдельного implementation commit и
  прикладывает desktop/phone screenshots.

## LOG

### 2026-08-11 — Specification

Область ограничена двумя файлами: существующий browser suite становится полным
и самодостаточным, а визуальные исправления остаются в общем stylesheet. Новых
API и pixel snapshots нет. Контракт и проверяемые обещания записаны в
`knowledge/specs/full-visual-audit-desktop-mobile.md`.
