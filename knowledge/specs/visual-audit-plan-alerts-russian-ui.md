# Спецификация: План, Уведомления и единый русский интерфейс

## Цель и влияние на владельца

Владелец получает компактные страницы intake: обоснование в карточке Плана
открывается только по явному действию, а Уведомления сначала показывают
недавние события в сворачиваемых группах. На desktop и телефоне фильтры,
раскрытия и действия доступны без горизонтальной прокрутки, наложений и
обрезки.

Основные страницы control plane используют единый русский язык. Английские
названия разделов, статусов и действий больше не смешиваются с русскими
подписями. Идентификаторы, URL, имена моделей, API-значения, названия стадий
workflow и команды остаются техническими данными и не переводятся.

## Технический подход и реальные файлы

Фактический `intake/plan.py` уже обслуживает `/plan` и `/alerts`: сейчас
`why` выводится непосредственно в карточке, а `/alerts` читает JSONL по
`/opt/factory-data/pilot/notifications.jsonl`, имеет default `n=100` и
выводит отдельные события. Реализация меняет только HTML/CSS-представление и
безопасный test seam пути журнала; форматы записей, `ideas_json`, действия и
публичные API не меняются.

1. В `intake/plan.py` непустой `why` рендерится внутри доступного
   `<details>` с понятным `<summary>`. Заголовок, badges, метаданные и действия
   карточки остаются видимыми, значение продолжает экранироваться.
2. `/alerts` сохраняет параметр `group` и порядок «свежее сначала», но без
   параметров ограничивается 30 записями в безопасном диапазоне. Отобранные
   события группируются по `GROUP_RU`: summary содержит название, число и
   время последнего события. Нефильтрованные группы закрыты; единственная
   явно выбранная группа раскрыта. Внутри сохраняются title, message,
   timestamp, quiet flag и исходная ссылка.
3. Существующий intake CSS в том же модуле получает только необходимые
   responsive-правила: перенос длинного текста, гибкие tabs и доступные
   размеры controls на ширине 390 px.

В `web/src/App.tsx` находятся фактические названия навигации и topbar. В
`Work.tsx`, `Workers.tsx`, `Repositories.tsx`, `Workflows.tsx`, `Cards.tsx`,
`Automations.tsx` и `Settings.tsx` меняется только owner-facing copy,
aria-label, empty/error/action text. Маршруты, query keys, модели и API
payloads остаются прежними. Неизменный словарь:

| Сущность | Подпись владельцу |
| --- | --- |
| Work / task detail | Работы / Задача |
| Workers / worker detail | Исполнители / Исполнитель |
| Repositories / repository detail | Репозитории / Репозиторий |
| Workflows / workflow detail | Сценарии / Сценарий |
| Cards | Карточки |
| Automations / automation detail | Автоматизации / Автоматизация |
| Settings | Настройки |
| Delegate task / Assign work | Поставить задачу / Назначить работу |
| Repository / Status | Репозиторий / Статус |
| Online / Offline / Last seen | В сети / Не в сети / Последний контакт |
| sessions / active / retained | сеансы / занято / сохранено |

`Factory`, `GitHub`, `Markdown`, `CLI`, `Cron`, `UTC`, provider/runtime names,
machine IDs, repository remote identity, поле `runtime`, stage keys (`Triage`,
`Specification`, `Review`, `Verify`) и команды не переводятся. Английское
API-значение состояния отображается русским label без изменения передаваемого
значения.

Подтверждённые дефекты layout исправляются точечно в `web/src/Epics.tsx`,
`web/src/Automations.tsx`, `web/src/Workers.tsx`, `web/src/Settings.tsx` и
`web/src/styles.css`: перенос toolbar эпиков, responsive filter bar,
переносимые worker metadata/actions и Settings-навигация. Settings получает
якоря разделов и верхнее сохранение с той же mutation/validation семантикой,
что у нижней кнопки; нижняя кнопка остаётся.

`web/e2e/server.mjs` запускает только Go control plane, поэтому новый
`web/e2e/intake-fixture.py` монтирует реальный `intake.plan.router` с
детерминированным facade `pilot` и временным JSONL. Он намеренно не импортирует
тяжёлый `intake/app.py`. Новый `web/e2e/intake.spec.ts` открывает настоящие
`/plan` и `/alerts` в 1440×1000 и 390×844, выполняет disclosure/filter
interactions, проверяет отсутствие document-level horizontal overflow и
сохраняет четыре снимка. Существующий `web/e2e/control-plane.spec.ts` остаётся
аудитом React control plane и обновляет selectors на русские подписи.

## Последовательный план

1. Добавить в `pilot/test_pilot.py` unit-проверки закрытого `why`, default 30,
   limit, group/filter и порядка событий.
2. Реализовать компактный HTML/CSS в `intake/plan.py`, не меняя формы,
   action semantics и формат JSONL.
3. Создать ASGI-фикстуру и Playwright-сценарий для реальных `/plan` и
   `/alerts`; проверить оба viewport и вручную просмотреть четыре снимка.
4. Внести словарь в перечисленные React-экраны, обновив role/name selectors в
   `web/src/App.test.tsx` и `web/src/Settings.test.tsx`.
5. Добавить только связанные responsive-классы, anchors и общее верхнее/нижнее
   сохранение Settings.
6. Выполнить целевые проверки и `git diff --check`; полный набор оставляется
   этапу Verify.

## Критерии приёмки

- На `/plan` заголовок, badges, metadata и действия видны сразу; непустой
  `why` не виден до открытия доступного раскрытия, после чего показывает
  исходный экранированный текст.
- `/alerts` без параметров показывает не более 30 свежих корректных записей;
  `group` оставляет выбранную группу. Группы по `GROUP_RU` сохраняют порядок,
  summary содержит имя, число и свежесть, а событие содержит все исходные
  пользовательские поля. Пустой и malformed журнал дают безопасный empty
  state.
- На 1440×1000 и 390×844 План, Уведомления, Epics, Automations, worker detail
  и Settings не имеют page-level horizontal overflow, наложений или
  недостижимых controls.
- Settings имеет работающие якоря и верхнее сохранение с той же семантикой,
  что нижнее.
- На перечисленных control-plane экранах нет английских user-facing heading,
  status, action, filter, empty/error text или aria-label вне технических
  исключений словаря; API, routes и технические значения не меняются.
- Browser-тест использует реальный router-backed `/plan` и `/alerts`, а
  существующий React visual audit проходит с русскими selectors в обоих
  viewport.

## Тест-план

- `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` с новыми
  handler-HTML проверками Плана и Уведомлений.
- `npm --prefix web test -- --run web/src/App.test.tsx web/src/Settings.test.tsx`
  для словаря, якорей и верхнего сохранения.
- `npm --prefix web run test:browser -- --grep "shows the real intake Plan and Alerts"`
  для реальных intake-страниц на desktop и phone.
- `npm --prefix web run test:browser -- --grep "audits every Factory screen on desktop and phone"`
  для обновлённого React visual audit.
- На Verify: один полный `npm --prefix web test -- --run`, typecheck, build,
  lint, browser suite и `git diff --check`.

## Риски и решения

- ASGI-фикстура тестирует реальный router, но не полный `intake/app.py`, чтобы
  несвязанная Whisper-зависимость не делала UI-проверку нестабильной.
- Default 30 выбран для компактного обзора. Иное значение или всегда раскрытая
  критическая группа требуют отдельного продуктового решения до Implement.
- Перевод затрагивает много assertions; запрещено механически переводить API
  значения и технические идентификаторы.
- Не добавлять новую React-страницу Уведомлений, API pagination, persistent
  state раскрытия или массовый редизайн таблиц. Новый source-файл вне
  перечисленного состава требует отдельного согласования.

## Карточка работы

`knowledge/cards/CARD-0073-visual-audit-plan-alerts-russian-ui.md`

Карточка `CARD-0174` закреплена за живой приёмкой и не является частью этой
работы. Ошибочный файл `CARD-0174-visual-audit-plan-alerts-russian-ui.md` не
создаётся.

ГОТОВО-КОГДА: файл intake/plan.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/e2e/intake-fixture.py
ГОТОВО-КОГДА: файл web/e2e/intake.spec.ts
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: файл web/src/App.tsx
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/Workers.tsx
ГОТОВО-КОГДА: файл web/src/Repositories.tsx
ГОТОВО-КОГДА: файл web/src/Workflows.tsx
ГОТОВО-КОГДА: файл web/src/Cards.tsx
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/Settings.tsx
ГОТОВО-КОГДА: файл web/src/Epics.tsx
ГОТОВО-КОГДА: файл web/src/styles.css
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: файл web/src/Settings.test.tsx
ГОТОВО-КОГДА: команда npm --prefix web run test:browser -- --grep "shows the real intake Plan and Alerts"
