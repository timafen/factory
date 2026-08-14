# Playwright доступен рантайму генератора отчётов

## Цель и влияние на владельца

Серверный генератор PDF импортирует пакет `playwright` непосредственно из
`web/report/render.mjs`. Сейчас в манифесте web-пакета объявлен только
`@playwright/test` как dev-зависимость. Поэтому чистая production-установка
`npm ci --omit=dev` не обязана поставить модуль, который нужен генератору
отчёта; ежедневный PDF может завершиться до запуска изолированного Chromium.

После изменения production-установка будет содержать точный пакет рантайма.
Владелец получает воспроизводимую поставку PDF-отчётов без зависимости от
инструментов тестирования. UI, формат отчёта, launcher и sandbox не меняются.

## Технический подход и реальные файлы

- В `web/package.json` добавить `playwright` в `dependencies`, не заменяя и не
  удаляя `@playwright/test`: последний остаётся инструментом browser-тестов.
- Обновить `web/package-lock.json` штатной npm-командой, чтобы корневой пакет и
  транзитивные записи отражали production-статус `playwright` и сохраняли
  согласованные закреплённые версии.
- Дополнить `web/report/report.test.mjs` проверкой контракта манифеста: модуль,
  который импортирует `web/report/render.mjs`, объявлен в runtime-зависимостях.
  Поведение renderer, его сетевой запрет и обязательный launcher не менять.
- `internal/controlplane/report_scripts/render.mjs` остаётся без изменений:
  он уже умеет загрузить `playwright` из установленного `web`-пакета, а
  `.github/workflows/dependency-audit.yml` остаётся потребителем контракта
  через `npm ci --omit=dev`.

## Последовательный план

1. Зафиксировать красный сценарий, проверяющий, что импортируемый renderer
   пакет объявлен в `dependencies`, а не только транзитивно у test runner.
2. Перенести прямую зависимость `playwright` в runtime-раздел манифеста и
   регенерировать lockfile соответствующей версией npm.
3. Выполнить чистую production-установку без dev-зависимостей и проверить
   динамический импорт `playwright` из каталога `web`.
4. Запустить целевой Node-набор renderer и проверить, что lockfile не содержит
   несогласованной корневой записи.

## Критерии приёмки

1. `web/package.json` объявляет `playwright` в `dependencies` с версией,
   согласованной с lockfile.
2. `@playwright/test` остаётся в `devDependencies`; browser-тестовый интерфейс
   и команды не меняются.
3. После `npm ci --omit=dev` из `web` команда `import("playwright")`
   завершается успешно.
4. `web/report/render.mjs` продолжает запускать Chromium только через
   обязательный абсолютный `FACTORY_BROWSER_LAUNCHER` и sandbox.
5. Изменения ограничены манифестом, lockfile и целевой регрессией; UI и
   production-скрипты не затрагиваются.

## Тест-план

- Новый/дополненный тест `web/report/report.test.mjs` читает манифест и
  подтверждает, что прямой импорт `playwright` renderer обеспечен runtime-
  зависимостью; до исправления он падает.
- Чистая проверка поставки: `npm --prefix web ci --omit=dev --ignore-scripts`
  и затем `node --input-type=module -e 'import("playwright")'` из `web`.
- Регрессия renderer: `node web/report/report.test.mjs`, включая создание PDF,
  недоступный launcher и запрет внешних загрузок.

## Риски и решения

- Риск: пакет может остаться доступен локально благодаря dev-зависимостям и
  скрыть дефект. Решение: обязательная чистая установка с `--omit=dev`.
- Риск: ручное редактирование lockfile рассинхронизирует дерево. Решение:
  обновлять его npm и проверять чистый `npm ci`.
- Риск: перенос `@playwright/test` в production расширит серверную поверхность
  без необходимости. Решение: добавить только `playwright`, нужный прямому
  импорту runtime.
- Вне области: скачивание браузера, настройки AppArmor/systemd sandbox,
  отчётный UI и политика dependency audit.

## Карточка работы

`knowledge/cards/CARD-0127-playwright-runtime-dependency.md`

ГОТОВО-КОГДА: файл web/package.json
ГОТОВО-КОГДА: файл web/package-lock.json
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: команда cd web && npm ci --omit=dev --ignore-scripts && node --input-type=module -e 'import("playwright")'
