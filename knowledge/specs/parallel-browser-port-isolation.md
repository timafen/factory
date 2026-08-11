# Изоляция адресов параллельных browser-проверок

## Цель и влияние на пользователя

Четыре параллельных потока Verify смогут одновременно запускать финальную
браузерную проверку. Сейчас каждый `just test-browser` поднимает fixture на
`127.0.0.1:17437`; второй процесс завершается на `bind: address already in
use` ещё до Playwright. После изменения каждый запуск получает собственный
loopback-адрес, поэтому независимые работы не ждут друг друга и не теряют
результат проверки из-за чужого процесса.

## Технический подход

Ввести небольшой Node-запускатор `web/e2e/browser-runner.mjs`, вызываемый
скриптом `test:browser` после существующей сборки и проверки `dist`. Он
выделяет свободный TCP-порт на `127.0.0.1`, формирует `FACTORY_E2E_BASE_URL`
и запускает Playwright с этим окружением. Выбранный адрес выводится одной
структурированной строкой для диагностики; это является метрикой факта и
времени выбора ресурса. Запускатор освобождает временный резерв порта только
непосредственно перед стартом fixture и при неудаче повторяет выделение в
ограниченном числе попыток, так что гонка между независимыми запусками не
превращается в ложное падение.

`web/playwright.config.ts` станет читать обязательный base URL из окружения:
им задаются `use.baseURL`, `webServer.url`, команда fixture и отдельные
каталоги отчёта/артефактов текущего запуска. Таким образом Playwright не
переиспользует сервер другого Verify и параллельные прогоны не перезаписывают
доказательства друг друга.

`web/e2e/server.mjs` примет тот же адрес вместо литерала `17437`: передаст
его в `factory-server -listen`, сформирует из него URL в обоих временных
worker/poller-конфигах и сохранит текущую очистку дочерних процессов. В
`web/e2e/control-plane.spec.ts` прямые API-контексты будут брать общий helper
base URL из окружения, как и `page.goto("/")` уже берёт его из Playwright.

Для регрессии добавить самостоятельную Node-проверку запуска browser-runner:
два процесса стартуют параллельно с облегчённым fixture-режимом, оба достигают
health endpoint и завершаются с кодом 0; тест проверяет два разных адреса и
диагностическую строку выделения порта. Это проверяет именно межпроцессную
изоляцию, а не два вызова функции внутри одного процесса.

Не меняются Go HTTP API, схема базы, бизнес-логика Verify, число Verify-потоков
и политика сетевой sandbox. Новый environment contract внутренний для browser
fixture; ручной прямой `playwright test` остаётся явно неподдерживаемым без
runner, поскольку корректный путь — `npm run test:browser`/`just test-browser`.

## План

1. Добавить в `web/e2e/browser-runner.mjs` безопасное выделение loopback-порта,
   ограниченный retry при bind-гонке, передачу окружения, уникальный run ID,
   cleanup дочернего Playwright и запись измерения выбора адреса.
2. Перевести `web/package.json` на запускатор, а `web/playwright.config.ts` —
   на `FACTORY_E2E_BASE_URL`: base URL, health URL, env webServer и каталоги
   результатов получают один run-scoped контракт.
3. Перевести `web/e2e/server.mjs` и все прямые `request.newContext` в
   `web/e2e/control-plane.spec.ts` на общий адрес; сохранить одинаковый URL
   для server, worker и legacy poller fixture.
4. Добавить тесты resolver/контракта конфигурации в
   `web/src/playwrightConfig.test.ts` и межпроцессную регрессию в новом
   `web/e2e/browser-runner.test.mjs` (либо в существующем Node test entry,
   если он уже предоставляет запуск subprocess).
5. Запустить целевую регрессию и затем `just test-browser`; на Verify один раз
   запустить `just check`, проверить отсутствие изменений `dist` и
   `git diff --check`.

## Критерии приёмки

- Два одновременных `just test-browser` завершаются с кодом 0 и не содержат
  `address already in use`, `EADDRINUSE` или иной отказ bind.
- Каждый прогон использует собственный адрес; server, временный worker,
  legacy poller, Playwright `baseURL`/health URL и все API-контексты обращаются
  только к адресу своего прогона.
- В журнальном выводе каждого прогона есть выбранный адрес и длительность его
  выделения; две параллельные проверки показывают разные адреса.
- Параллельные прогоны не смешивают Playwright artifacts/reports.
- Конфигурация сохраняет Chromium sandbox и bootstrap credential, а существующая
  последовательность build + проверка `dist` остаётся частью `test:browser`.
- Количество параллельных Verify не меняется: решение не добавляет глобальный
  browser-lock и не меняет `max_parallel_subtasks`.

## План тестирования

- Добавить unit-проверки, что configuration требует/использует переданный
  E2E base URL и строит согласованный health URL и run-scoped output paths.
- Добавить `node --test web/e2e/browser-runner.test.mjs`: две параллельные
  subprocess-проверки должны получить разные URL, дождаться health и выйти
  успешно; до реализации этот тест воспроизводит общий `17437`.
- На Implement: `cd web && node --test e2e/browser-runner.test.mjs` и
  `just test-browser`.
- На Verify: `just check`, `just test-browser`, `git diff --check` и проверка
  `git diff --exit-code -- web/dist`.

## Риски и решения

- Выбран динамический адрес вместо общего `flock`: lock проще, но превращает
  browser-фазу четырёх Verify в последовательную очередь. Это противоречит
  требованию не уменьшать параллелизм; поэтому ожидание lock не выбирается.
- Между освобождением временного резерва и bind fixture теоретически возможен
  внешний захват порта. Ограниченный retry запускатора делает это наблюдаемой
  и восстанавливаемой гонкой; interprocess-регрессия защищает главный случай
  двух Factory запусков. Перед реализацией не требуется менять Go server API.
- Уникальные каталоги результатов увеличат число CI artifacts за один job,
  но не их содержание; существующий upload `web/test-results/` и
  `web/playwright-report/` уже охватывает вложенные run ID.
- Не расширять задачу до изоляции production smoke `ops/test-browser-sandbox.sh`:
  он использует отдельный port `7337` и не является частью fixture Verify.

## Карточка

`knowledge/cards/CARD-0070-parallel-browser-port-isolation.md`

ГОТОВО-КОГДА: файл web/e2e/browser-runner.mjs
ГОТОВО-КОГДА: файл web/e2e/browser-runner.test.mjs
ГОТОВО-КОГДА: файл web/playwright.config.ts
ГОТОВО-КОГДА: файл web/e2e/server.mjs
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: файл web/src/playwrightConfig.test.ts
ГОТОВО-КОГДА: файл web/package.json
ГОТОВО-КОГДА: команда cd web && node --test e2e/browser-runner.test.mjs
