# Спецификация: ежедневный визуальный отчёт PDF

## Цель и влияние на владельца

Владелец получает на экране `/reports` историю ежедневных отчётов с PDF,
снимками «до/после» и метриками за выбранный день. Отчёт должен честно
показывать отсутствующий снимок, не раскрывать внутренние пути и не создавать
дубликаты при параллельном запуске. Опубликованная реализация уже есть;
этот этап фиксирует проверяемый контракт и продолжение CARD-0122.

## Технический подход и реальные файлы

- SQL-схема и durable-claim: `migrations/029_daily_visual_reports.sql`,
  `migrations/030_visual_report_claims.sql`.
- Сервис, сбор данных, метрики и PDF: `internal/controlplane/reports.go`,
  `internal/controlplane/report_runtime.go`.
- HTTP API, проверка SHA-256/размера и ошибки БД:
  `internal/controlplane/reports_http.go`.
- Capture/render через изолированный Chromium и inline PNG:
  `internal/controlplane/report_scripts/capture.mjs`,
  `internal/controlplane/report_scripts/render.mjs`,
  `web/report/capture.mjs`, `web/report/render.mjs`.
- Контракты и регрессии: `internal/controlplane/reports_test.go`,
  `internal/controlplane/reports_http_test.go`, `web/report/report.test.mjs`.
- Экран и маршрутизация: `web/src/Reports.tsx`, `web/src/Reports.test.tsx`
  (маршрут `/reports` подключён в существующей web-навигации).

## Последовательный план

1. Перенести CARD-0122 без изменения её номера и сохранить implementation
   commit `270854f9d720299b94411f78f6fb310cabf48d17`.
2. В тесте ошибки БД устранить повторный `Store.Close` в `t.Cleanup`;
   cleanup должен закрывать ресурс ровно один раз и не маскировать ожидаемый
   5xx от закрытой БД.
3. Выполнить целевой Go-тест с `-count=5`, затем UI/Node проверки отчёта.
4. После этого проверить живой `/reports` системным Chromium; при отсутствии
   launcher/Chromium записать находку и не объявлять карточку закрытой.

## Критерии приёмки

- За прошедший день создаётся не более одного durable PDF на timezone.
- PDF начинается с `%PDF-`, содержит проверенные inline-снимки и метрики
  «до/после»; отсутствующий capture явно помечен `missing`.
- Скачать можно только готовый PDF с совпадающими путём, размером и SHA-256;
  ошибки БД дают 5xx без panic.
- `/reports` показывает историю и ссылку на скачивание, а malformed URL и
  недоступный capture обрабатываются безопасно.
- Cleanup-тест ошибки БД проходит 5/5; живая проверка `/reports` PASS либо
  отдельно зафиксирована как инфраструктурно невозможная.

## Тест-план

- `go test ./internal/controlplane -run '^TestDailyReportDownloadReturnsServerErrorWhenDatabaseFails$' -count=5`
- `go test ./internal/controlplane -run 'DailyReport|VisualReport'`
- `node --test web/report/report.test.mjs`
- `npm run typecheck`, `npm run lint`, `npm run build`
- Системный Chromium: открыть живой `/reports`, увидеть историю, метрики,
  состояния «до/после» и скачать PDF.

## Риски и решения

- Повторное закрытие Store в cleanup: сделать cleanup идемпотентным в тесте,
  не менять поведение production Store.
- Просроченный renderer может перезаписать новый отчёт: claim-token,
  уникальное имя и проверка `RowsAffected` остаются обязательными.
- SSRF/утечка локальных файлов: только allowlist host, изолированный launcher,
  sandbox и inline-ресурсы.
- Нет системного Chromium или стенда: пометить проверку BLOCKED находкой,
  сохранив целевые автоматические проверки зелёными.

## Карточка работы

Продолжение `knowledge/cards/CARD-0122-daily-visual-report-pdf.md`.
Работа этого этапа документирует дубликат и критерии продолжения, не меняя
продуктовый код и UI.

ГОТОВО-КОГДА: файл internal/controlplane/reports.go
ГОТОВО-КОГДА: файл internal/controlplane/report_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_http.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_test.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_http_test.go
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: файл web/src/Reports.tsx
ГОТОВО-КОГДА: команда git diff --check
