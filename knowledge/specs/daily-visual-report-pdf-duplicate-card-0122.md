# Спецификация: ежедневный PDF продолжается только в CARD-0122

## Цель и влияние на владельца

Закрыть текущую постановку как дубликат уже реализуемого ежедневного визуального
отчёта и не создавать второй PDF-конвейер. Владелец должен получить один экран
`/reports`, один отчёт за локальный календарный день, проверяемые снимки «до» и
«после» и понятное сравнение метрик с предыдущим днём. Источником реализации и
последующей приёмки остаётся только `CARD-0122-daily-visual-report-pdf` в ветке
`factory/28591ece-f5d-5baef51e-932`.

Текущая Specification не меняет продуктовый код и не разрешает слияние
кандидата. База проверки `main` зафиксирована как
`73f4edce272cb113607540412425d842158e2b81`, кандидат CARD-0122 — как
`a4c55bdee4deb554f5f7e35756045a43f0584836`. Ветка кандидата содержит
непустой diff, но её карточка сообщает о блокирующем падении нового Go-теста;
поэтому дальнейшее слияние допустимо только после отдельного Review PASS и
однократного полного Verify.

## Технический подход и реальные файлы

Повторная реализация не требуется. Фактический кандидат CARD-0122 уже содержит
следующие части, которые Review обязан оценивать как единую поставку:

- `migrations/029_daily_visual_reports.sql` и
  `migrations/030_visual_report_claims.sql` создают visual targets, durable
  captures, ежедневные отчёты и claim-токены для безопасного повторного запуска;
- `internal/protocol/types.go`, `internal/controlplane/store.go` и
  `internal/controlplane/state.go` принимают visual target, не выдают root task
  до terminal-состояния `before` и ставят `after` после нужной успешной стадии;
- `internal/controlplane/captures.go`, `internal/controlplane/reports.go`,
  `internal/controlplane/report_runtime.go` и встроенные scripts реализуют
  sandboxed capture, повторяемую сборку PDF, проверку PNG/hash и календарные
  метрики; `cmd/factory-server/main.go` управляет обоими фоновыми сервисами;
- `internal/controlplane/reports_http.go` и `internal/controlplane/http.go`
  публикуют защищённые list/download endpoints с проверкой timezone, размера и
  SHA-256 готового PDF;
- `web/report/capture.mjs`, `web/report/render.mjs` и
  `ops/install-server-browser.sh` используют изолированный browser launcher,
  allowlist хостов и локальные ресурсы без внешних запросов при PDF-render;
- `web/src/DelegateModal.tsx` задаёт URL, точный видимый текст и viewport, а
  `web/src/Reports.tsx`, `web/src/App.tsx`, `web/src/api.ts`, `web/src/types.ts`
  и `web/src/styles.css` дают владельцу русскоязычный список и скачивание;
- Go-, Vitest-, Node- и shell-тесты кандидата покрывают retry, отсутствие
  ложного «до», завершение `after`, timezone/DST, конкурентные claims,
  повреждённый PDF, browser isolation и видимые статусы.

Сгенерированные `web/dist`-артефакты входят в тот же кандидат и должны быть
пересобраны из исходников, а не редактироваться вручную. `CARD-0122` изменяется
только в своей канонической ветке; эта дублирующая работа ведёт отдельную
карточку закрытия `CARD-0159`.

## Последовательный план

1. Закрыть текущую постановку как дубликат CARD-0122 без продуктового diff и
   без переноса исходников из ветки кандидата.
2. В канонической ветке CARD-0122 сделать cleanup теста ошибки БД идемпотентным,
   чтобы `TestDailyReportDownloadReturnsServerErrorWhenDatabaseFails` стабильно
   завершался с кодом 0 и проверял именно HTTP 5xx, а не повторный `Store.Close`.
3. Начать Review с нового remote default branch, зафиксировать полные SHA и
   сравнить только `<base_sha>...<candidate_sha>`; проверить весь список файлов,
   миграции, claim ownership, SSRF/browser isolation, download integrity и UI.
4. При Review PASS выполнить Verify: целевые Go/Node/UI проверки, typecheck и
   production build, затем ровно один полный Go- и web-набор. Чужой flaky-тест
   отделить от дефекта области согласно правилам конвейера.
5. Проверить `/reports` глазами на стенде, если доступен установленный Chromium
   и launcher; отсутствие инфраструктуры записать как находку, не подменяя её
   служебной страницей.
6. Сливать только проверенную каноническую ветку CARD-0122. CARD-0159 завершить
   как `CLOSED / DUPLICATE` и не создавать из неё Implement + Test.

## Критерии приёмки

1. Текущая ветка содержит только эту спецификацию и отдельную карточку закрытия;
   исходники приложения, UI, миграции и карточка CARD-0122 не изменены.
2. Канонический кандидат сохраняет максимум один отчёт на пару дата/timezone,
   безопасно возвращает просроченные claims и не позволяет старому renderer
   перезаписать результат нового владельца claim.
3. Визуальная root task не стартует до terminal `before`; отсутствующий снимок
   остаётся явным placeholder с причиной, а `after` создаётся только после
   заданной успешной стадии в тех же URL/state/viewport.
4. Capture допускает только валидный абсолютный URL и разрешённый host через
   абсолютный изолированный launcher с Chromium sandbox; PDF renderer не делает
   внешних запросов и встраивает только проверенные PNG.
5. Download выбирает точную timezone, повторно проверяет размер и SHA-256 и
   возвращает 5xx при ошибке БД вместо panic либо повреждённого PDF.
6. `/reports` показывает человеку дату, timezone, понятный статус, метрики
   «текущий день против предыдущего», число визуальных результатов и ссылку
   только на готовый PDF — без голых идентификаторов и машинных статусов.
7. Review имеет статус PASS только после устранения детерминированного падения
   теста закрытой БД; Verify подтверждает типы, сборку, целевые и полные наборы.

## Тест-план

- Обязательная проверка сути:
  `sh -c "grep -q 'func TestDailyVisualReportKeepsMissingBeforeHonest' internal/controlplane/reports_test.go && go test ./internal/controlplane -run '^TestDailyVisualReportKeepsMissingBeforeHonest$'"`.
- Регрессия ошибки БД:
  `go test ./internal/controlplane -run '^TestDailyReportDownloadReturnsServerErrorWhenDatabaseFails$' -count=5`;
  пять запусков должны завершиться с кодом 0 после исправления cleanup.
- Целевой backend:
  `go test ./internal/controlplane -run 'TestVisualCapture|TestSuccessfulConfiguredStage|TestDailyReport'`.
- Browser/PDF: `cd web && node --test report/report.test.mjs`.
- UI, типы и сборка: `cd web && npm test -- --run src/Reports.test.tsx`,
  `npm run typecheck`, `npm run build`.
- На Verify ровно один раз: `go test -timeout 5m ./...` и полный `npm test` в
  `web`; отдельно зафиксировать внешний flaky `internal/worker`, если повторится.
- Для этой Specification: `git diff --check` и трёхточечный список файлов
  относительно свежего `origin/main`.

## Риски и решения

- Две опубликованные спецификации уже могут породить повторный Implement.
  Решение: текущая карточка имеет terminal-статус duplicate, а единственным
  источником кода и Review остаётся CARD-0122.
- В карточке кандидата уже записан красный тест ошибки БД. Решение: не объявлять
  PASS по старым результатам; сначала исправить только cleanup и повторить тест
  пять раз, затем заново зафиксировать SHA кандидата.
- Скриншоты могут содержать секреты или персональные данные. Решение: закрытый
  report root, существующая авторизация API, allowlist URL и отсутствие внешних
  ресурсов при render; срок хранения остаётся отдельным решением владельца.
- Рестарт или зависший renderer может дать дубликат/перезапись. Решение:
  уникальность дата/timezone, claim-токены, stale takeover и атомарная публикация
  файла с повторной проверкой hash/size.
- Chromium/launcher может отсутствовать на стенде. Решение: Node-тест доказывает
  контракт изоляции, а Verify явно отмечает инфраструктурную находку и не выдаёт
  ссылку на `/reports` без визуального результата.
- Полный Go-набор ранее видел сторонний flaky lease renewal. Решение: отделять
  чужую нестабильность от целевых тестов отчёта, но не игнорировать красноту в
  новых файлах CARD-0122.

## Карточка работы

`knowledge/cards/CARD-0159-daily-visual-report-pdf-duplicate.md`

ГОТОВО-КОГДА: файл cmd/factory-server/main.go
ГОТОВО-КОГДА: файл cmd/factory-server/main_test.go
ГОТОВО-КОГДА: файл internal/controlplane/captures.go
ГОТОВО-КОГДА: файл internal/controlplane/captures_test.go
ГОТОВО-КОГДА: файл internal/controlplane/claiming.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/report_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/capture.mjs
ГОТОВО-КОГДА: файл internal/controlplane/report_scripts/render.mjs
ГОТОВО-КОГДА: файл internal/controlplane/reports.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_http.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_http_test.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_test.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл migrations/029_daily_visual_reports.sql
ГОТОВО-КОГДА: файл migrations/030_visual_report_claims.sql
ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл web/dist/assets/index-B8WVVNc8.js
ГОТОВО-КОГДА: файл web/dist/assets/index-BA2KjUqx.js
ГОТОВО-КОГДА: файл web/dist/assets/index-Cbw03m_q.css
ГОТОВО-КОГДА: файл web/dist/assets/index-DV9BuM-r.css
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/report/capture.mjs
ГОТОВО-КОГДА: файл web/report/render.mjs
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: файл web/src/App.tsx
ГОТОВО-КОГДА: файл web/src/DelegateModal.tsx
ГОТОВО-КОГДА: файл web/src/Reports.test.tsx
ГОТОВО-КОГДА: файл web/src/Reports.tsx
ГОТОВО-КОГДА: файл web/src/api.ts
ГОТОВО-КОГДА: файл web/src/styles.css
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/vite.config.ts
ГОТОВО-КОГДА: команда sh -c "grep -q 'func TestDailyVisualReportKeepsMissingBeforeHonest' internal/controlplane/reports_test.go && go test ./internal/controlplane -run '^TestDailyVisualReportKeepsMissingBeforeHonest$'"
