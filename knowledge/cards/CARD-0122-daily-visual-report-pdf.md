# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 7bebf0ec418cb50bb65ecd7c2d69a0b63a556d07 — PDF ждёт готовности обязательных снимков и автоматически собирается после рестарта

## HEAD

- Status: SPECIFIED — ожидает реализацию поставки browser runtime штатным релизом.
- Branch: `factory/e8d83036-21a-49f5b4f9-956`
- Implementation commit: `7bebf0ec418cb50bb65ecd7c2d69a0b63a556d07`
- What changed: зафиксирован следующий дефект поставки: после чистого `fx factory release` PDF renderer не должен зависеть от вручную подготовленных `/opt/factory`, `node_modules`, Chromium или launcher.
- Evidence: текущий renderer требует абсолютный `FACTORY_BROWSER_LAUNCHER` и `playwright`, а `ops/fx-factory-release` публикует Go/control-plane artifacts без browser payload; критерии и целевой fixture-тест записаны в `knowledge/specs/daily-pdf-clean-standard-release.md`.
- One next action: реализовать атомарную поставку и rollback pinned browser runtime через штатный release.

## LOG

### 2026-08-14 — Specification

После triage определён воспроизводимый разрыв: ручная установка
`ops/install-server-browser.sh` делает PDF работоспособным, однако полный штатный
release не включает browser payload в generation и после удаления build checkout
renderer может не найти `playwright`. Спецификация требует чистую fixture без
`/opt/factory`-зависимостей, установку до остановки служб, readiness/sandbox smoke
и rollback browser runtime вместе с server. Product code и UI на этом этапе не
менялись.

### 2026-08-13 — Implement

После замечания Review ежедневный PDF больше не публикуется без обязательной пары
снимков: незавершённые, отсутствующие или недоступные capture оставляют durable-задание
в `pending`, поэтому новый процесс автоматически продолжает сборку. Интеграционный тест
воспроизводит гонку запуска и рестарт, а затем находит обе PNG-вставки в единственном PDF;
10 целевых повторов, полный Go-набор, 179 UI- и 4 Node-теста, lint, typecheck и обе сборки прошли.

### 2026-08-13 — Implement

После замечания Review production PDF renderer больше не запускает Chromium без изоляции:
абсолютный `FACTORY_BROWSER_LAUNCHER` обязателен, sandbox включён, недоступный launcher
завершает рендер ошибкой. Добавлен прямой поведенческий тест production-скрипта и исправлено
чтение stdin; 4 Node-теста, Go-контрольный пакет, lint, typecheck, build и smoke `%PDF-` прошли.

### 2026-08-13 — Implement

Устранено последнее блокирующее падение: тест ошибки БД открывает отдельное
хранилище и после намеренного закрытия проверяет именно ответ 5xx. После rebase
state-машина сохранила и retry автоматизаций, и постановку снимка `after`;
`web/dist` пересобран. Регрессия прошла 5/5, полный Go-набор и 179 web-тестов,
Node PDF, browser shell, lint, typecheck и production build завершились успешно.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Ежедневный PDF со снимком и метриками | `npm test`; `node report/report.test.mjs` | PASS: UI-набор зелёный, renderer создал `%PDF-` со встроенным PNG без внешних запросов. |
| Защищённый capture и целостность скачивания | Node allowlist/sandbox-тест; Go-тесты report API | BLOCKED: Node-защита PASS, но новый Go-тест закрытой БД падает 5/5 при повторном `Store.Close` из cleanup. |
| Сборка и регрессии | `go test -timeout 5m ./...`; `npm run lint`; `npm run typecheck`; `npm run build` | Web PASS; полный Go-набор также поймал внешний flaky `internal/worker` по разбросу lease renewal. |
| Живая проверка `/reports` | Проверка системного browser launcher | Не выполнена: Chromium и `/usr/local/bin/factory-browser-launcher` на стенде отсутствуют. |

### 2026-08-13 — Implement

Закрыты M1–M3 и minor из остановленного Review: capture использует только абсолютный изолирующий launcher, `chromiumSandbox: true` и список разрешённых хостов; URL разбирается до обращения к hostname; report runtime инициализируется после recovery mode; SQL-сбой скачивания возвращает 5xx. Целевые Go-, UI-, Node- и browser installer тесты, TypeScript, lint и production build прошли.

### 2026-08-13 — Implement

Исправлены находки Review F1–F5 и риск целостности: фоновой capture-worker переводит снимки через durable states и повторяет сбой, успешная заданная стадия ставит `after`, PDF встраивает проверенные PNG и календарное сравнение двух дней. Claim-токены и уникальные имена не дают просроченному renderer перезаписать новый отчёт; download требует точный timezone и пересчитывает SHA-256. Целевые тесты покрывают снимки, повтор, `after`, DST/часовые пояса, конкурентную сборку и повреждённый PDF. Полные Go- и UI-наборы, lint, typecheck, production build, сборка бинарников и Chromium PDF-тест прошли.

### 2026-08-13 — Implement

Подключена суточная фоновая генерация отчёта за прошедший день. Строка `daily_reports` служит одновременно журналом и блокировкой от дублей; ошибки renderer становятся повторяемыми, а просроченный `running` можно безопасно забрать после сбоя. Тест автоматического старта зафиксировал один временный сбой, успешный повтор, PDF-сигнатуру и ровно одну итоговую запись. Полные Go- и web-наборы (174 UI-теста), Node PDF-тест, typecheck и production build прошли.

### 2026-08-13 — Implement

Добавлены схема хранения visual target/capture/report, блокировка claim до terminal `before`, защищённые report API, локальные capture/PDF scripts и русскоязычный экран отчётов. Обязательный тест `TestDailyVisualReportKeepsMissingBeforeHonest` сначала зафиксирован красным из-за отсутствующей реализации, затем прошёл. Полные Go- и web-наборы, typecheck, production build и отдельный Node-тест `%PDF-` зелёные.
