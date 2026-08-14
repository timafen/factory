# Спецификация: ежедневный PDF после чистого штатного релиза

## Цель и влияние на владельца

После обычного `fx factory release` ежедневный PDF должен снова собираться сам,
даже если на сервере нет checkout `/opt/factory` и заранее установленных там
`node_modules`. Владельцу не требуется заходить на хост, выполнять `npm i playwright`
или вручную чинить Chromium. Неуспешная подготовка browser runtime должна честно
остановить выпуск до смены работающей версии, а не проявиться ночью пустым отчётом.

Фактический разрыв: `internal/controlplane/report_scripts/render.mjs` и
`capture.mjs` при отсутствии локального ESM-пакета ищут `playwright` относительно
`process.cwd()/web/package.json`. Штатный `ops/fx-factory-release` выполняет
`npm ci` только во временном `$work/src/web`, публикует лишь перечисленные файлы и
удаляет `$work`; browser installer в транзакцию выпуска не вызывается. Ручная
установка в `/opt/factory/web` маскирует этот разрыв, но не является поставкой.

## Технический подход и реальные файлы

- В `ops/fx-factory-release` ввести постоянные поколения browser runtime под
  release root и атомарную ссылку `current`. В новое поколение из проверенного
  candidate копируются `web/package.json`, `web/package-lock.json`, report scripts
  и browser helpers; `npm ci`/установка Chromium выполняются до остановки служб.
- Browser runtime становится частью release transaction: manifest хранит его
  fingerprint, post-install проверяет `current`, Playwright, launcher, readiness
  marker и PDF smoke. При позднем сбое ссылка и привилегированные browser-файлы
  возвращаются к предыдущему поколению вместе с server/worker; неудачное входящее
  поколение не публикуется.
- В `ops/install-server-browser.sh` разделить проверенный source payload и
  постоянный runtime target, сохранив lockfile-pinned Chromium, AppArmor,
  allowlist, `chromiumSandbox: true`, идемпотентность и собственный rollback.
  Неизменный fingerprint не скачивает Chromium повторно, но readiness smoke
  остаётся обязательным.
- В `internal/controlplane/report_scripts/render.mjs` и `capture.mjs` заменить
  fallback через `process.cwd()` на единый `FACTORY_BROWSER_PAYLOAD` с production
  default, совпадающим с release `current`. Абсолютный
  `FACTORY_BROWSER_LAUNCHER` остаётся обязательным; fallback без sandbox запрещён.
- В `ops/test-fx-factory-release.sh` добавить чистую fixture без `/opt/factory`,
  browser cache, launcher и `node_modules`. Она должна пережить удаление build
  checkout, выполнить production renderer и получить `%PDF-`; отдельные сценарии
  фиксируют installer failure и поздний rollback.
- `ops/test-install-server-browser.sh` проверяет разделение source/runtime,
  повторную установку без скачивания и восстановление прежнего browser state.
  `web/report/report.test.mjs` проверяет поиск Playwright только в постоянном
  payload и сохранение изоляции renderer/capture.

## Последовательный план

1. Зафиксировать путь, владельца, права и fingerprint постоянного browser runtime,
   а также единый контракт `FACTORY_BROWSER_PAYLOAD`.
2. Научить installer собирать входящее поколение из lockfile без зависимости от
   текущего каталога службы или `/opt/factory` и безопасно откатывать свои файлы.
3. Добавить подготовку browser runtime в release после зелёных ворот, но до первой
   остановки службы; включить payload и readiness evidence в manifest поколения.
4. Атомарно публиковать browser `current` вместе с поколением Factory и возвращать
   прежний `current`/launcher/profile во всех существующих путях rollback.
5. Перевести embedded capture/renderer на постоянный payload и добавить clean-host
   smoke после удаления временного checkout.
6. Закрепить успех, повтор, ранний отказ и поздний rollback целевыми shell/Node
   тестами; существующие Go-тесты отчёта подтверждают отсутствие ложного `ready`.

## Критерии приёмки

1. Штатный выпуск на чистом хосте без `/opt/factory` сам устанавливает pinned
   Playwright/Chromium и launcher, создаёт readiness marker и завершается с кодом 0.
2. После удаления `$work/src` production renderer импортирует Playwright из
   опубликованного browser `current` и создаёт файл с сигнатурой `%PDF-`.
3. Ежедневный report/capture использует абсолютный изолированный launcher,
   Chromium sandbox и прежний host allowlist; небезопасного fallback нет.
4. Отсутствующий модуль, Chromium, launcher, readiness marker или неуспешный smoke
   запрещает публикацию выпуска и не останавливает работающие службы.
5. Повтор того же выпуска не скачивает неизменный Chromium, но повторно доказывает
   готовность runtime; поздний сбой восстанавливает согласованные server и browser.
6. Ни runtime, ни тест не читает и не изменяет `/opt/factory`; ручная установка на
   production не входит в процедуру восстановления.

## Тест-план

- `bash ops/test-fx-factory-release.sh`: новая чистая fixture проверяет install,
  удаление checkout, `%PDF-`, отсутствие мутаций при installer failure и возврат
  предыдущего browser поколения при позднем rollback.
- `bash ops/test-install-server-browser.sh`: pinned install, readiness/sandbox smoke,
  идемпотентный повтор и rollback browser-файлов в изолированном временном root.
- `node --test web/report/report.test.mjs`: production scripts находят Playwright
  через `FACTORY_BROWSER_PAYLOAD`, требуют launcher и не ослабляют sandbox.
- `go test ./internal/controlplane -run 'DailyReport|VisualReport'`: durable retry,
  ожидание снимков и публикация только валидного PDF остаются зелёными.

## Риски и решения

- Установка Chromium долгая и зависит от сети. Она идёт до остановки служб;
  fingerprint пропускает неизменное скачивание, а любой сбой оставляет старый
  выпуск рабочим.
- `node_modules` нельзя копировать из произвольного рабочего checkout. Постоянное
  поколение строится только `npm ci` по committed lockfile под пользователем
  `factory`, а manifest связывает fingerprint с candidate SHA.
- Launcher, AppArmor и Chromium cache живут вне обычного списка Go-артефактов.
  Их прежнее состояние сохраняется до commit release и восстанавливается тем же
  rollback, иначе согласованный выпуск не считается завершённым.
- Параллельные или повторные релизы могут спорить за `current`. Существующий общий
  release lock охватывает подготовку и публикацию browser runtime; входящие пути
  уникальны и становятся видимыми только через атомарную ссылку.

## Карточка работы

Текущая работа ведётся отдельно в
`knowledge/cards/CARD-0166-daily-pdf-clean-release-runtime.md`. Старая
`CARD-0122` описывает создание самого отчёта и не изменяется этой поставкой.

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/render.mjs
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/capture.mjs
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
