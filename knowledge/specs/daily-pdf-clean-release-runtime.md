# Ежедневный PDF после чистого штатного выпуска

## Цель и влияние на владельца

Владелец должен получать ежедневный PDF и обязательные снимки сразу после
обычного `fx factory release`, даже если в `/opt/factory/web` нет `node_modules`
и никто вручную не выполнял там `npm install` или `npm i playwright`.

Сейчас штатный выпуск запускает `npm ci` только в `$work/src/web`. Этот каталог
сборки очищается в `cleanup`, тогда как встроенные
`internal/controlplane/report_scripts/{render,capture}.mjs` запускаются из
`FACTORY_REPORT_ROOT/runtime` и при неудаче ищут Playwright относительно
`process.cwd()/web/package.json`. На боевом сервере это связывает результат с
случайно сохранённым checkout `/opt/factory`. Одновременно
`ops/install-server-browser.sh` умеет подготовить Chromium, но текущий
`ops/fx-factory-release` его не вызывает.

Результат поставки: release сам подготавливает устойчивый, привязанный к
`web/package-lock.json` Node runtime в `FACTORY_DATA_HOME`, проверяет его тем же
изолированным Chromium и передаёт абсолютный путь именно PDF- и capture-процессам.
Исходный checkout, его текущий каталог и ручные действия владельца не участвуют
в работе отчёта.

## Технический подход и реальные файлы

1. `ops/install-server-browser.sh` получает управляемый runtime-каталог с
   дефолтом под `FACTORY_DATA_HOME` (например,
   `$FACTORY_DATA_HOME/browser-runtime`). Установщик копирует из кандидатного
   payload только `web/package.json` и `web/package-lock.json` в новый
   versioned runtime, запускает от пользователя Factory
   `npm ci --omit=dev --no-audit --no-fund`, убеждается через `node` в
   разрешении `playwright`, затем ставит/проверяет Chromium из **этого** runtime.
   `web/package.json` уже содержит `playwright` в `dependencies`, поэтому
   отдельное изменение зависимостей не требуется.

2. Runtime публикуется атомарно: до smoke используется новая временная
   версия, а ссылка `current` меняется только после успешной проверки
   sandbox/allowlist. В state установщика сохраняются digest lock-файла,
   абсолютный путь активного runtime и fingerprint Chromium. При неизменном
   lock runtime и Chromium не скачиваются заново; при ошибке прежний runtime,
   launcher, state и readiness marker остаются рабочими. Все пути должны быть
   абсолютными, реальными каталогами с проверенными владельцем и режимами;
   symlink из непроверяемого места не принимается.

3. `ops/fx-factory-release` вызывает установщик с кандидатным
   `FACTORY_BROWSER_SHARE=$work/src` и управляемым runtime **до**
   `stop_factory_units`. Успех подготовки становится обязательным pre-cutover
   gate: ошибка возвращает ненулевой код, не останавливает server/worker и не
   требует ручной установки в `/opt/factory`. Для ошибки после подготовки
   release сохраняет прежнюю ссылку runtime и восстанавливает её тем же
   rollback-путём, что и остальные артефакты выпуска.

4. `cmd/factory-server/main.go` вычисляет единственный абсолютный путь
   `package.json` активного browser runtime из `FACTORY_DATA_HOME`; опциональный
   override допустим лишь для абсолютного пути и нужен для изолированных тестов.
   Этот путь передаётся обоим сервисам, а не выводится из рабочего каталога
   процесса.

5. `internal/controlplane/reports.go` и `internal/controlplane/captures.go`
   передают в дочерний `node` одинаковую переменную
   `FACTORY_REPORT_PACKAGE_JSON`. В
   `internal/controlplane/report_scripts/render.mjs` и `capture.mjs` удаляется
   fallback через `process.cwd()` и неявный `import("playwright")`; оба скрипта
   проверяют абсолютный путь и загружают Playwright только через
   `createRequire(FACTORY_REPORT_PACKAGE_JSON)`. Недоступный runtime остаётся
   видимой, повторяемой ошибкой задания, но не заставляет искать модуль в
   `/opt/factory`.

6. `cmd/factory-server/main_test.go`,
   `internal/controlplane/reports_test.go` и
   `internal/controlplane/captures_test.go` фиксируют выбор управляемого пути и
   его передачу дочерним процессам. `web/report/report.test.mjs` запускает
   production-скрипт из отдельного пустого cwd с явным package path, чтобы
   доказать отсутствие зависимости от checkout. Shell-регрессии в
   `ops/test-install-server-browser.sh` и
   `ops/test-fx-factory-release.sh` проверяют подготовку, очистку build-clone,
   порядок до cutover, idempotency и rollback.

## Последовательный план

1. Добавить в server код функцию выбора browser runtime: дефолт под
   `FACTORY_DATA_HOME`, строгая проверка абсолютного пути и тестовый override.
   Передать пакетный путь конструктору report- и capture-сервисов.

2. Изменить command-реализации renderer/capturer так, чтобы они добавляли
   `FACTORY_REPORT_PACKAGE_JSON` в окружение конкретного `node`-процесса.
   Обновить оба embedded MJS: один механизм `createRequire`, понятная ошибка
   для отсутствующего/относительного/неразрешаемого runtime.

3. Переделать browser installer в поставщик постоянного runtime: staging по
   digest lock-файла, `npm ci --omit=dev` от пользователя Factory, Chromium и
   smoke из staging, атомарный `current`, сохранение предыдущего состояния.
   Не писать зависимости в `/opt/factory` и не использовать его как fallback.

4. Включить installer в `fx-factory-release` как обязательный pre-cutover
   шаг. Передать только пути fixture/candidate через существующие переменные,
   проверить возврат ненулевого статуса до остановки служб и восстановление
   прежней runtime-ссылки при последующем rollback.

5. Добавить изолированные Go/Node/shell-регрессии. Положительный сценарий
   стартует с пустым runtime и без `/opt/factory/web/node_modules`, завершает
   release, удаляет временный clone и создаёт PNG/PDF. Отрицательные сценарии
   проверяют ошибку installer, недоступный package path, относительный путь и
   смену lock-файла.

6. После реализации обновить эту карточку фактическим кодовым коммитом и
   результатами целевых проверок; UI и существующий контракт API отчётов не
   менять.

## Критерии приёмки

1. Чистый штатный release с пустым изолированным runtime завершается успешно
   и создаёт управляемый package root с Playwright из кандидатного
   `package-lock.json`; ни один шаг не выполняет `npm` в `/opt/factory`.

2. После очистки `$work/src` и при произвольном cwd server-процесса capture
   находит Playwright по переданному абсолютному package path, создаёт валидный
   PNG, а renderer создаёт файл, начинающийся с `%PDF-`.

3. `render.mjs` и `capture.mjs` не содержат fallback по `process.cwd()` и не
   разрешают неявный модуль; отсутствующий или относительный package path
   завершается понятной ошибкой, не обращаясь к `/opt/factory`.

4. Release вызывает browser installer до первой остановки служб. Его ошибка
   возвращает ненулевой код, не запускает cutover и оставляет старые binary,
   browser runtime и readiness marker нетронутыми.

5. Повторный release с тем же lock-файлом использует активный runtime и
   Chromium без повторной загрузки. Изменение lock-файла готовит новую версию,
   проходит smoke и атомарно активирует её; неудача сохраняет предыдущую.

6. Chromium по-прежнему запускается только через существующий абсолютный
   launcher с `chromiumSandbox: true`; allowlist и Basic Auth smoke не
   ослабляются.

7. Публичные API `/api/v1/reports` и экран «Отчёты» сохраняют контракт; эта
   поставка меняет только доставку runtime и надёжность фонового PDF.

## Тест-план

| Уровень | Сценарий | Ожидаемое доказательство |
| --- | --- | --- |
| Go | Выбор default/override runtime и окружение renderer/capturer | Оба `node`-процесса получают один абсолютный `FACTORY_REPORT_PACKAGE_JSON`; относительный или отсутствующий путь безопасно отклонён. |
| Node | Production `render.mjs` и `capture.mjs` из materialized runtime | Пустой cwd и отсутствие `/opt/factory/web/node_modules` не влияют на разрешение пакета; PDF/PNG создаются из управляемого package root. |
| Installer | Новый runtime, тот же lock, изменённый lock, ошибка smoke | `npm ci --omit=dev` выполняется только в managed staging; current меняется лишь после smoke; прежнее состояние сохранено при ошибке. |
| Release | Чистая fixture, успешный и неуспешный browser gate | Installer вызывается до `stop_factory_units`; success переживает cleanup build-clone, failure не меняет службы и не требует ручного `/opt/factory` шага. |
| Регрессия sandbox | Launcher, Chromium и network allowlist | Существующие негативные проверки sandbox и Basic Auth остаются зелёными. |

Полный целевой прогон после реализации включает release-, installer- и
production-renderer сценарии. Обязательная команда ниже запускает расширенную
installer-регрессию: в ней должен быть добавлен изолированный сценарий с пустым
runtime, удалённым payload и разрешением Playwright только из managed пути; она
должна завершаться с кодом 0.

## Риски и решения

| Риск | Решение |
| --- | --- |
| Временный clone снова станет неявным runtime | Скрипты принимают только абсолютный `FACTORY_REPORT_PACKAGE_JSON`; тест удаляет clone до PDF. |
| Новый runtime окажется активен при неудачном release | Versioned staging и атомарная `current`-ссылка; release сохраняет и восстанавливает прежнюю ссылку при rollback. |
| `npm ci` будет каждый раз тратить время или загружать Chromium | Сравнивать digest lock-файла и fingerprint; неизменную проверенную версию переиспользовать, но smoke не пропускать. |
| Dev-зависимости попадут в production | Использовать `npm ci --omit=dev`; проверить, что `playwright` остаётся runtime dependency в lock-файле. |
| Подмена пути или ослабление sandbox | Принимать только проверенный абсолютный package path внутри managed root; launcher, AppArmor, allowlist и `chromiumSandbox: true` оставить обязательными. |
| Тест докажет лишь вызов shell, но не живой PDF | Комбинировать fixture release с Node production-скриптом, который создаёт `%PDF-` после удаления исходного checkout. |

## Карточка работы

Текущая работа ведётся только в
`knowledge/cards/CARD-0304-daily-pdf-clean-release-runtime.md`. Она продолжает
диагностику поставки runtime и не меняет ранее закрытую карточку функции
ежедневного отчёта. Реализация должна обновить только эту карточку своим
фактическим кодовым коммитом.

## Файлы реализации

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл cmd/factory-server/main.go
ГОТОВО-КОГДА: файл cmd/factory-server/main_test.go
ГОТОВО-КОГДА: файл internal/controlplane/reports.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_test.go
ГОТОВО-КОГДА: файл internal/controlplane/captures.go
ГОТОВО-КОГДА: файл internal/controlplane/captures_test.go
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/render.mjs
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/capture.mjs
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: команда bash ops/test-install-server-browser.sh
