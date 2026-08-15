# Спецификация: компактные План и Уведомления, русский интерфейс

## Цель и влияние на владельца

Владелец должен быстро понять, что требует внимания: обоснование карточки
Плана открывается только по явному действию, а Уведомления по умолчанию дают
не более 30 свежих событий в сворачиваемых тематических группах. На desktop и
телефоне фильтры, раскрытия и действия остаются видимыми и достижимыми.

Control plane говорит с владельцем по-русски на основных экранах и в detail
экранах. Технические данные — ID, URL, CLI, provider, runtime, Cron, UTC и
workflow keys — сохраняют исходное написание.

## Технический подход и реальные файлы

`intake/plan.py` сейчас выводит `why` без раскрытия, а `/alerts` строит до 100
отдельных карточек. Здесь нужны семантические `<details>`: для непустого
обоснования Плана и для групп Уведомлений. Сортировка остаётся «свежее
сначала», фильтр `group` сохраняется, default становится 30, а группа содержит
имя, число и время свежего события. Без фильтра группы закрыты; выбранная
группа открыта. Формат JSONL, действия Планa и публичные API не меняются.

`web/e2e/server.mjs` обслуживает React control plane, поэтому `/plan` и
`/alerts` проверяются отдельной FastAPI ASGI-фикстурой `web/e2e/intake-fixture.py`,
подключающей настоящий `intake.plan.router` с детерминированными данными и
временным JSONL. При необходимости путь журнала инъецируется только через
test seam с прежним production default.

Навигация и topbar сосредоточены в `web/src/App.tsx`; owner-facing тексты и
aria-label обновляются в `Work.tsx`, `Workers.tsx`, `Repositories.tsx`,
`Workflows.tsx`, `Cards.tsx`, `Automations.tsx`, `Settings.tsx`,
`TaskDetail.tsx`, `DelegateModal.tsx`, `TaskFilePicker.tsx`, `format.ts` и
`ui.tsx`. `html lang` становится `ru`. API payload, route path, query key и
значение статуса не переводятся; английское значение отображается русским
label только на UI.

Точечные классы в `Epics.tsx`, `Automations.tsx`, `Workers.tsx` и
`Settings.tsx`, а также правила в `styles.css`, исправляют переносы и сетки.
Settings получает якорное оглавление и ровно одну заметную закреплённую кнопку
сохранения, использующую прежние validation и mutation. На 1440×1000 и
390×844 не должно быть document-level horizontal overflow, наложения или
обрезанного интерактивного элемента.

Все файлы реализации: `intake/plan.py`, `pilot/test_pilot.py`,
`web/e2e/intake-fixture.py`, `web/e2e/intake.spec.ts`,
`web/e2e/control-plane.spec.ts`, `web/e2e/server.mjs`,
`web/playwright.config.ts`, `web/src/App.tsx`, `web/src/App.test.tsx`,
`web/src/Work.tsx`, `web/src/Workers.tsx`, `web/src/Repositories.tsx`,
`web/src/Workflows.tsx`, `web/src/Cards.tsx`, `web/src/Automations.tsx`,
`web/src/Epics.tsx`, `web/src/Settings.tsx`, `web/src/Settings.test.tsx`,
`web/src/TaskDetail.tsx`, `web/src/DelegateModal.tsx`,
`web/src/TaskFilePicker.tsx`, `web/src/TaskFilePicker.test.tsx`,
`web/src/format.ts`, `web/src/format.test.ts`, `web/src/ui.tsx`,
`web/src/ui.test.tsx`, `web/src/styles.css`, `web/src/playwrightConfig.test.ts`
и генерируемые `web/dist/index.html`, `web/dist/assets/*`.

## Последовательный план

1. Добавить Python-проверки handler HTML: скрытое `why`, лимит 30, filter,
   группы и порядок Уведомлений.
2. Реализовать compact intake HTML/CSS без изменения form actions, журнала и API.
3. Добавить router-backed ASGI fixture и Playwright `/plan`, `/alerts` с четырьмя
   снимками на обоих viewport.
4. Перевести owner-facing copy и селекторы тестов; технические строки не менять.
5. Добавить адаптивные классы для Epics, Automations, worker detail и Settings;
   оставить одну закреплённую кнопку сохранения с теми же validation/mutation.
6. Прогнать целевые проверки, затем один полный набор на Verify и `git diff --check`.

## Критерии приёмки

- `/plan` оставляет title, badges, metadata и действия видимыми; непустой `why`
  появляется только после доступного раскрытия, полностью и с HTML-escaping.
- `/alerts` без параметров показывает не более 30 свежих корректных записей;
  `group` фильтрует их. Группы следуют `GROUP_RU`, сохраняют порядок внутри,
  summary содержит название, число и свежесть; событие сохраняет title,
  message, timestamp, quiet-признак и click link.
- На Epics, Automations, worker detail и Settings нет overflow, наложения,
  обрезки либо недостижимых действий в 1440×1000 и 390×844.
- Settings имеет работающие якоря и ровно одну заметную закреплённую кнопку
  «Сохранить настройки» с прежними validation и mutation.
- Work, Workers, Repositories, Workflows, Cards, Automations, Settings,
  detail-экраны и выбор файлов используют русский owner-facing язык; `html lang="ru"`.
- Отдельный Playwright-сценарий открывает реальные `/plan` и `/alerts`,
  раскрывает Plan/Alerts, применяет фильтр и сохраняет четыре снимка.
- Общий React visual audit проходит на двух viewport с русскими селекторами.

## Тест-план

- `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` с новыми HTML
  assertions для Плана и Уведомлений.
- `npm --prefix web test -- --run web/src/App.test.tsx web/src/Settings.test.tsx web/src/TaskFilePicker.test.tsx`.
- `npm --prefix web run test:browser -- --grep "shows the real intake Plan and Alerts"`.
- `npm --prefix web run test:browser -- --grep "audits every Factory screen on desktop and phone"`.
- На Verify: полный Vitest, typecheck, lint, build, полный browser suite,
  `just check` и `git diff --check`.

## Риски и решения

- Полный `intake/app.py` тянет несвязанную тяжёлую voice-зависимость; ASGI fixture
  намеренно монтирует реальный `intake.plan.router`, а не копирует шаблон.
- Default 30 — договорённость о компактном обзоре; расширение через безопасный
  параметр `n` остаётся. Иное поведение критических групп требует решения владельца.
- Массовый перевод может случайно изменить технические значения. Рецензия
  проверяет только copy, aria-label и presentation mapping.
- Вне области: новый React route Уведомлений, API pagination, persistent state
  disclosure, pixel-snapshot gate и общий редизайн остальных экранов.

## Карточка работы

`knowledge/cards/CARD-0073-visual-audit-plan-alerts-russian-ui.md`

ГОТОВО-КОГДА: файл intake/plan.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/e2e/intake-fixture.py
ГОТОВО-КОГДА: файл web/e2e/intake.spec.ts
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: файл web/e2e/server.mjs
ГОТОВО-КОГДА: файл web/playwright.config.ts
ГОТОВО-КОГДА: файл web/src/App.tsx
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/Workers.tsx
ГОТОВО-КОГДА: файл web/src/Repositories.tsx
ГОТОВО-КОГДА: файл web/src/Workflows.tsx
ГОТОВО-КОГДА: файл web/src/Cards.tsx
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/Epics.tsx
ГОТОВО-КОГДА: файл web/src/Settings.tsx
ГОТОВО-КОГДА: файл web/src/Settings.test.tsx
ГОТОВО-КОГДА: файл web/src/TaskDetail.tsx
ГОТОВО-КОГДА: файл web/src/DelegateModal.tsx
ГОТОВО-КОГДА: файл web/src/TaskFilePicker.tsx
ГОТОВО-КОГДА: файл web/src/TaskFilePicker.test.tsx
ГОТОВО-КОГДА: файл web/src/format.ts
ГОТОВО-КОГДА: файл web/src/format.test.ts
ГОТОВО-КОГДА: файл web/src/ui.tsx
ГОТОВО-КОГДА: файл web/src/ui.test.tsx
ГОТОВО-КОГДА: файл web/src/styles.css
ГОТОВО-КОГДА: файл web/src/playwrightConfig.test.ts
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/dist/assets/*
ГОТОВО-КОГДА: команда npm --prefix web run test:browser -- --grep "shows the real intake Plan and Alerts"
