# Спецификация: ежедневный PDF после чистого штатного релиза

## Цель и влияние на владельца

После обычного `fx factory release` ежедневный PDF должен собираться сам: владельцу
не нужно входить на хост и вручную ставить Node-модули, Playwright, Chromium или
launcher в `/opt/factory`. Сейчас фоновый renderer запускает `node` и требует
абсолютный `FACTORY_BROWSER_LAUNCHER`, а его скрипт загружает `playwright` из
`web/package.json`; release-transaction кладёт в новое поколение только Go-бинарники
и control-plane файлы. Поэтому чистый штатный релиз может закончиться успешно, но
первый ежедневный PDF перейдёт в `error` из-за отсутствующей browser-зависимости.

## Технический подход и реальные файлы

- `ops/fx-factory-release` должен считать browser runtime частью полного поколения:
  до рестарта server установить проверенный browser payload из candidate, а его
  готовность включить в transaction, rollback и post-install runtime verification.
  Нельзя опираться на удаляемую после релиза `$work/src` или на прежний
  `/opt/factory` checkout.
- `ops/install-server-browser.sh` уже ставит lockfile-закреплённые Node-модули,
  Playwright Chromium, AppArmor-профиль и `/usr/local/libexec/factory/factory-browser-sandbox`.
  Его нужно сделать вызываемым из release с постоянным явным payload path и
  идемпотентным состоянием; сбой подготовки обязан остановить release до замены
  работающего поколения.
- `internal/controlplane/report_scripts/render.mjs` и `internal/controlplane/reports.go`
  должны получать путь к постоянному browser payload через явно установленное
  окружение/контракт release, а не через текущую директорию службы `/opt/factory`.
  Сохраняются обязательные абсолютный launcher и `chromiumSandbox: true`.
- `ops/factory-browser-sandbox`, `ops/factory-browser-isolated` и browser payload
  (lockfile, renderer/capture scripts) включаются в проверяемый inventory поколения;
  `ops/test-fx-factory-release.sh` проверяет чистую fixture без заранее созданных
  `node_modules` и Chromium, а `ops/test-install-server-browser.sh` остаётся
  изолированной проверкой installer-а.
- `internal/controlplane/reports_test.go` и `web/report/report.test.mjs` остаются
  контрактными регрессиями: неготовый runtime не публикует ложный PDF, а готовый
  renderer создаёт файл `%PDF-` через изолированный launcher.

## Последовательный план

1. Зафиксировать постоянный root browser payload и переменные release/browser runtime;
   не использовать `/opt/factory` как неявную зависимость.
2. Добавить browser payload и installer в immutable manifest нового поколения,
   включая резервирование и восстановление его прежнего состояния при rollback.
3. Вызвать installer после проверки candidate и до остановки Factory-служб; требовать
   успешный sandbox smoke и readiness marker до публикации поколения.
4. Передать server-у постоянный путь к payload/launcher так, чтобы embedded
   `render.mjs` всегда нашёл ту же pinned версию `playwright` после удаления build tree.
5. Расширить чистую release fixture: успешный релиз устанавливает зависимости и
   генерирует PDF; ошибка installer-а не меняет server, worker, browser runtime или
   release-info и не перезапускает службы.

## Критерии приёмки

1. На хосте без `/opt/factory`, `node_modules`, Playwright cache и launcher штатный
   release сам создаёт постоянный browser runtime и завершает проверку с кодом 0.
2. После удаления временного checkout фоновый daily-report renderer импортирует
   pinned `playwright`, использует абсолютный изолированный launcher и создаёт PDF
   с сигнатурой `%PDF-`.
3. Нельзя объявить release успешным, если отсутствуют Node/Chromium/launcher,
   sandbox smoke или readiness marker; прежнее полное поколение остаётся рабочим.
4. Повтор того же release не переустанавливает неизменившие lockfile, Chromium и
   launcher, но всё равно проверяет их готовность.
5. Rollback восстанавливает согласованную пару server/browser runtime, а не оставляет
   новый PDF runtime вместе со старым сервером.

## Тест-план

- Новый сценарий в `ops/test-fx-factory-release.sh` стартует с пустых
  `/opt/factory`-эквивалента, browser cache и `node_modules`; проверяет install,
  запуск PDF renderer после удаления candidate checkout и `%PDF-`.
- Тот же тест имитирует отказ installer-а и подтверждает отсутствие установки,
  рестартов и частичного browser state.
- `bash ops/test-install-server-browser.sh` проверяет pinned install, повторный
  запуск, launcher, sandbox и readiness marker в отдельной временной директории.
- `go test ./internal/controlplane -run 'DailyReport|VisualReport'` и
  `node --test web/report/report.test.mjs` подтверждают durable-PDF контракт.

## Риски и решения

- Скачивание браузера увеличивает время и сетевую зависимость release. Установка
  происходит до остановки служб; failure закрывает release без мутации поколения,
  а lockfile/state делают повтор идемпотентным.
- Нельзя копировать `node_modules` из рабочего checkout: это непроверяемый,
  платформозависимый артефакт. Источник — lockfile и installer под пользователем
  `factory`; manifest хранит только доверенный payload и его fingerprint.
- Chromium требует privileged AppArmor/systemd настройки. Сохраняются существующие
  sandbox, allowlist и smoke; никакого fallback на обычный Chromium или `--no-sandbox`.
- Полный rollback browser runtime сложнее бинарного. До реализации нужно определить
  атомарный persistent payload root и сохранять предыдущие файлы/state до их замены.

## Карточка работы

Продолжение `knowledge/cards/CARD-0122-daily-visual-report-pdf.md`; implementation
commit карточки сохраняется, потому что эта работа устраняет релизную поставку уже
реализованного ежедневного PDF, не создавая вторую карточку отчёта.

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/render.mjs
ГОТОВО-КОГДА: файл internal/controlplane/reports.go
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: команда bash ops/test-fx-factory-release.sh
