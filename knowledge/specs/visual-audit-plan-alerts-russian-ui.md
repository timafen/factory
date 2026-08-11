# Спецификация: План, Уведомления и единый русский интерфейс

## Goal and user impact

Владелец видит на страницах intake компактный, а не бесконечный поток данных:
у карточки Плана обоснование открывается только по явному действию, а
Уведомления по умолчанию показывают недавние события, собранные в сворачиваемые
группы. На desktop и телефоне можно добраться до фильтров, раскрытия и действий
без горизонтальной прокрутки, наложений и обрезки элементов.

Основные экраны control plane говорят с владельцем единым русским языком.
Английские названия разделов, статусов и действий перестают смешиваться с
русскими подписями; идентификаторы, URL, имена моделей, значения API, названия
workflow-этапов и команды остаются техническими данными и не переводятся.

## Текущее поведение и граница задачи

- `intake/plan.py` рендерит каждое `why` прямо в `card_html`; `/alerts` читает
  последние 800 строк журнала, разворачивает их по времени и по умолчанию
  показывает до 100 отдельных карточек (`n` допускает 300). Его tabs только
  отфильтровывают группу, а не собирают результат в компактные группы.
- `/plan` и `/alerts` обслуживаются реальным FastAPI intake-приложением
  (`intake/app.py` подключает `plan_router`), но `web/e2e/server.mjs` запускает
  только Go control plane. Нынешний Playwright-аудит поэтому не открывает эти
  HTML-страницы.
- В `web/src/App.tsx` навигация и topbar всё ещё содержат `Work`, `Workers`,
  `Repositories`, `Workflows`, `Cards`, `Automations`, `Settings`,
  `Delegate task` и английские detail-названия. Компоненты перечисленных
  разделов содержат оставшиеся пользовательские английские тексты; например,
  `Automations.tsx` — фильтры и пустые состояния, `Workers.tsx` — статусы,
  sessions и profile/detail-подписи, `Settings.tsx` — ошибки валидации.
- `Epics.tsx` использует inline flex-строки, `Automations.tsx` не задаёт
  отдельную responsive-компоновку filter bar, `Workers.tsx` имеет длинные
  detail-строки, а `Settings.tsx` — длинную форму с единственным сохранением
  внизу. Общий stylesheet уже содержит responsive-запросы для 980/760 px,
  поэтому точечные классы добавляются в `web/src/styles.css`, а не создаётся
  второй слой layout-системы.

Вне области: изменение бизнес-состояний, API и источника журнала уведомлений,
перевод технических идентификаторов/CLI-команд, пиксельные snapshot-сравнения,
а также редизайн остальных неупомянутых экранов. Расширение полного аудита
CARD-0068 на эти два intake-экрана — отдельное дополнение, не пересмотр его
исходного списка React routes.

## Technical approach

### Intake: компактные данные без изменения backend-контракта

1. В `intake/plan.py` выводить `why` внутри семантического `<details>` с
   понятным `<summary>` (например, «Показать обоснование»). Заголовок, тип,
   состояние, метаданные и доступные действия карточки остаются сразу видимыми;
   значение `why`, причины и тексты сохраняются и экранируются как сейчас.
2. Для `/alerts` оставить существующий параметр `group` и порядок «свежее
   сначала», но снизить default до 30 событий и ограничить query-параметр тем
   же безопасным диапазоном. После фильтра собрать выбранные события в
   `GROUP_RU`-группы, сохранив временной порядок внутри каждой. Каждая группа
   рендерится как `<details>` с summary «<группа> · <число>» и временем
   последнего события; при явном `group` единственная группа раскрыта, в
   неотфильтрованном виде группы закрыты. Событие внутри группы сохраняет
   title, message, время, признак тихого события и исходную ссылку.
3. Дополнив имеющийся CSS intake, обеспечить перенос длинного текста, гибкие
   tabs и доступный размер summary/кнопок на 390 px. Никаких новых JSON API,
   мутаций или изменений форм `idea_action` не вводить.

### Русский словарь и layout control plane

Ввести в интерфейс следующий неизменный словарь и обновить роли/labels в
тестах вместе с текстом UI:

| Сущность | Пользовательская подпись |
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
поле `runtime`, machine IDs, repository remote identity, workflow-stage keys
(`Triage`, `Specification`, `Review`, `Verify`) и команды отображаются без
перевода. Там, где API отдаёт английское значение состояния, UI показывает
русский label, но не меняет передаваемое значение.

`App.tsx` остаётся единственным местом навигационных названий и topbar. В
`Work.tsx`, `Workers.tsx`, `Repositories.tsx`, `Workflows.tsx`, `Cards.tsx`,
`Automations.tsx` и `Settings.tsx` заменить только owner-facing copy,
aria-label и empty/error/action text согласно словарю. Модели, запросы,
query keys и API payloads не меняются.

Для подтверждённых layout-дефектов добавить минимальные классы и правила в
`styles.css`: переносимый toolbar эпиков, компактный flex/grid filter bar
автоматизаций, переносимые metadata/actions worker detail и settings-навигацию.
`Settings.tsx` получает список якорных разделов после заголовка и доступное
сохранение сверху (то же mutation/validation, что у нижней кнопки); нижняя
кнопка остаётся. На телефоне список якорей переносится и не создаёт overflow.

### Проверка настоящих intake-страниц в браузере

Добавить тестовую ASGI-фикстуру в `web/e2e`, которая монтирует именно
`intake.plan.router`, задаёт детерминированный facade `pilot` и временный
JSONL-журнал. Она не импортирует тяжёлый `intake/app.py` (его Whisper-модель
не нужна для данных Плана), но браузер получает реальный HTML обработчиков
`/plan` и `/alerts`, а не копию шаблона. Если для пути журнала нужен injection,
`intake/plan.py` читает его из специальной переменной окружения с текущим
production-путём как default; формат журнала и production-default не меняются.

Новый Playwright-сценарий открывает оба URL через эту ASGI-фикстуру при
1440×1000 и 390×844, проверяет смысловой heading, отсутствие document-level
горизонтального overflow и обрезанных интерактивных элементов, раскрывает
обоснование Плана, меняет фильтр Уведомлений и раскрывает группу. Он сохраняет
четыре screenshots для ручного просмотра. Существующий
`audits every Factory screen on desktop and phone` остаётся тестом React
control plane; его selectors и screenshots обновляются на русские labels.

## Affected modules/files

- `intake/plan.py` — lazy evidence карточки, recent/grouped alerts, responsive
  intake CSS и test-only configurable путь журнала с прежним default.
- `pilot/test_pilot.py` — unit-проверки HTML Плана и Уведомлений на реальных
  handler-функциях: скрытое `why`, default/limit, порядок, group/filter.
- `web/e2e/intake-fixture.py` — изолированное ASGI-окружение реального
  `intake.plan.router` с seeded data; не production service.
- `web/e2e/intake.spec.ts` — browser coverage `/plan` и `/alerts` в обоих
  viewport и screenshots.
- `web/e2e/control-plane.spec.ts` — русские selectors и полный React-аудит
  после изменения подписей.
- `web/src/App.tsx`, `web/src/Work.tsx`, `web/src/Workers.tsx`,
  `web/src/Repositories.tsx`, `web/src/Workflows.tsx`, `web/src/Cards.tsx`,
  `web/src/Automations.tsx`, `web/src/Settings.tsx` — glossary-only copy;
  также семантические classes/anchors, требуемые для точечных layout fixes.
- `web/src/Epics.tsx`, `web/src/styles.css` — подтверждённые desktop/mobile
  layout fixes без изменения бизнес-логики.
- `web/src/App.test.tsx`, `web/src/Settings.test.tsx` — обновлённые selectors
  и проверки русских навигационных подписей, anchors и верхнего сохранения.

Данных и публичных API не добавляется. Единственный test seam — путь JSONL
уведомлений, сохраняющий `/opt/factory-data/pilot/notifications.jsonl` как
production default.

## Plan

1. Сначала написать Python unit-тесты, фиксирующие свернутое `why`, 30
   недавних Уведомлений, group summary, выбранный фильтр и сохранённый порядок.
2. Реализовать compact HTML/CSS в `intake/plan.py`, не меняя `ideas_json`,
   actions, формы и format notification records.
3. Добавить ASGI fixture и Playwright-тест для реальных `/plan` и `/alerts`;
   прогнать его на desktop и phone, затем вручную просмотреть четыре снимка.
4. Внести glossary в React-экраны и обновить существующие role/name selectors.
5. Добавить classes и только связанные responsive-правила для Epics,
   Automations, worker detail и Settings; в Settings добавить anchors и общий
   верхний/нижний save action.
6. Дополнить Vitest и React e2e assertions, затем выполнить целевые проверки
   и `git diff --check`. Полный набор оставляется этапу Verify.

## Acceptance criteria

### План

- На `/plan` карточка показывает заголовок, badges, metadata и действия сразу;
  непустое обоснование не отображается до открытия доступного раскрытия.
- Открытие раскрытия показывает исходный полный текст `why`; его HTML-escaping
  и действия карточки не регрессируют.
- На 1440×1000 и 390×844 tabs, карточка, disclosure и действия помещаются без
  document-level horizontal scroll, наложения или clipped control.

### Уведомления

- `/alerts` без параметров показывает не более 30 самых свежих корректных
  записей; `group` оставляет только выбранную группу.
- События сгруппированы по `GROUP_RU`, внутри каждой остаются «свежее сначала»;
  summary содержит имя, число и свежесть, а событие раскрывает title, message,
  timestamp, quiet flag и click link.
- Неотфильтрованный вид компактен (группы закрыты); явная группа раскрыта и
  видна пользователю. Пустой и malformed журнал продолжают давать безопасное
  empty state.

### Layout и язык

- На Epics, Automations, worker detail и Settings при 1440×1000 и 390×844 нет
  page-level horizontal overflow, наложения или недостижимых действий.
- Settings имеет работающие якоря разделов и верхнее сохранение, использующее
  ту же validation/mutation семантику, что и нижняя кнопка.
- На Work, Workers, Repositories, Workflows, Cards, Automations и Settings нет
  английского user-facing heading, status, action, filter, empty/error text
  или aria-label, кроме утверждённых технических исключений словаря.
- Nav/topbar/detail labels следуют словарю, а данные API, route paths,
  query-keys, status values, CLI/ID/provider/runtime/UTC/Cron не меняются.

### Browser coverage

- Отдельный Playwright-тест открывает реальный router-backed `/plan` и
  `/alerts`, выполняет их disclosure/filter interactions и сохраняет снимки
  `plan-{desktop,phone}` и `alerts-{desktop,phone}`.
- Существующий общий React visual audit проходит с русскими ready selectors в
  обоих viewport; screenshots остаются ручным доказательством, а не pixel
  snapshot gate.

## Test plan

- `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` плюс новые тесты
  handler-HTML в том же модуле: компактность Плана и grouping/filtering Alerts.
- `npm --prefix web test -- --run web/src/App.test.tsx web/src/Settings.test.tsx`
  — словарь, верхнее сохранение и якоря Settings.
- `npm --prefix web run test:browser -- --grep "audits intake plan and alerts on desktop and phone"`
  — router-backed intake browser proof.
- `npm --prefix web run test:browser -- --grep "audits every Factory screen on desktop and phone"`
  — обновлённый React visual audit.
- На Verify один раз: `npm --prefix web test -- --run`, `npm --prefix web run
  typecheck`, `npm --prefix web run build`, `npm --prefix web run lint`, полный
  browser suite и `git diff --check`.

## Risks and decisions

- ASGI fixture проверяет ровно `intake.plan.router`, но не запускает полный
  `intake/app.py`, поскольку импорт последнего тянет голосовую Whisper-модель
  и сделал бы UI-тест зависимым от ML-runtime. Это осознанный баланс: HTML и
  роуты реальные, тяжёлая несвязанная часть не участвует.
- Default 30 — решение для компактного рабочего обзора; параметр `n` остаётся
  для просмотра большего числа событий в безопасной верхней границе. Если
  владелец хочет иной default или всегда раскрытую критическую группу, это
  требует продуктового решения до Implement.
- Перевод всех строк `Automations.tsx` и worker detail затрагивает много
  assertions. Механическое переименование технических API значений запрещено;
  реализация должна менять только copy/labels и обновлять selectors.
- Scope creep: не добавлять новую страницу уведомлений в React, API pagination,
  persistent state раскрытия или массовый редизайн таблиц. Любой новый source
  файл вне списка Affected modules/files требует согласования.

## Card

`knowledge/cards/CARD-0070-visual-audit-plan-alerts-russian-ui.md`

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
ГОТОВО-КОГДА: команда npm --prefix web run test:browser -- --grep "audits intake plan and alerts on desktop and phone"
