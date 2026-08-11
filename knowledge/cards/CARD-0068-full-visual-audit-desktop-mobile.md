# CARD-0068 — Полный визуальный аудит Factory на компьютере и телефоне

Implementation commit: 11bd56c1f27d82c38f2c0f0c31407086bdad5508 — аудит выявляет выходящие и обрезанные интерактивные элементы

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/294beb15-1ec-b4eba6f8-024`
- Implementation commit: `11bd56c1f27d82c38f2c0f0c31407086bdad5508`
- What changed: полный аудит всех экранов теперь разрешает исключения только для
  явных horizontal scrollers и проверяет их границы. Overflow и обрезание
  интерактивных элементов, включая нативные `main button`, стали assertions.
- Evidence: после rebase typecheck, production build и lint завершились с exit
  code 0; Vitest — 14 файлов, 147 тестов; полный Playwright — 20 passed (3.4m),
  включая целевой аудит 22 состояний в двух viewport (44 снимка, 1.1m).
- Next action: человеку влить `factory/294beb15-1ec-b4eba6f8-024` в `main`.

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

### 2026-08-11 — Verify

| Критерий | Команда или проверка | Наблюдаемый результат |
| --- | --- | --- |
| Чистая установка и статические ворота | `npm ci`; `npm run typecheck`; `npm run build`; `npm run lint` | Установка и все три ворота завершились с exit code 0; committed `dist` воспроизведён без diff. |
| Полный unit suite | `npm test` | 14 test files passed, 147 tests passed. |
| Все browser-регрессии | `FACTORY_BROWSER_LAUNCHER=/tmp/factory-browser-launcher-not-present npm run test:browser` | 20 tests passed за 3.4m; штатный системный launcher обойдён из-за запрета `sudo` политикой контейнера. |
| 22 состояния на desktop и phone | Playwright `audits every Factory screen on desktop and phone` | Целевой сценарий прошёл за 1.1m; сохранены 22 desktop и 22 phone screenshot. |
| Геометрия и ошибки браузера | Assertions каждого состояния | Нет page/main overflow, обрезанных interactive controls, вышедших scroller'ов, sticky-overlap, console errors и failed requests; synthetic regression обнаружила оба вида обрезания. |
| Визуальная пригодность | Ручной просмотр contact sheets и рискованных Overview, Projects, Settings, Delegate | Смысловой контент виден; desktop-иерархия сохранена; phone-поля, действия, переносы и модаль доступны. |
| Целостность Git | `git diff --check origin/main...HEAD`; проверка implementation commit | Diff-check чист; `11bd56c1f27d82c38f2c0f0c31407086bdad5508` — предок ветки и меняет `web/e2e/control-plane.spec.ts`. |
