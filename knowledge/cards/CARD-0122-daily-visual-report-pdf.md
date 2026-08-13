# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 3295c3c4c08c19bea1422224bd0695d11bbc0903 — ежедневный PDF пересобирается по отпечатку метрик и снимков, browser runtime установлен и проверяется при старте

## HEAD

- Status: PASS: четыре блокера Review устранены; общая проверка имеет только известную красноту вне области в `internal/worker`.
- Branch: `factory/92612d9e-15f-5f49be55-cd3`
- Implementation commit: `3295c3c4c08c19bea1422224bd0695d11bbc0903`
- What changed: `ready` PDF пересобирается только при новом отпечатке метрик или captures, включая поздний `after`; заменённый PDF удаляется.
- What changed: capture и render используют один root-owned Playwright runtime, явный launcher, Chromium sandbox и сетевую изоляцию; сервер fail-closed проверяет runtime при старте.
- Evidence: целевые Go-тесты, installer suite, 4 реальных Chromium-теста, UI 174/174, lint/typecheck и production builds → PASS.
- One next action: после установки нового browser runtime открыть `/reports` на стенде и скачать отчёт с поздним снимком «после».

## LOG

### 2026-08-13 — Implement

Исправлено повторное закрытие БД в обязательном тесте: прямое закрытие отказавшего соединения больше не сопровождается cleanup-владельцем `Store`. Целевой тест прошёл 5/5, полный Go-набор и web/PDF проверки зелёные; живой `/reports` не проверен из-за отсутствующих launcher/Chromium и root-доступа.

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

### 2026-08-13 — Implement

Устранены четыре блокера Review. Отпечаток входных метрик и снимков делает публикацию идемпотентной и одновременно пересобирает готовый PDF после позднего `after`; установленный Playwright runtime теперь общий для capture/render, запускается через sandbox/allowlist launcher и проверяется сервером до старта служб. Целевые Go-тесты, installer suite, четыре сценария на установленном Chromium, 174 UI-теста, lint/typecheck и обе production-сборки прошли. Полный Go-набор подтвердил `internal/controlplane`, но поймал известный flaky вне области: `internal/worker/TestConcurrentAttemptsStaggerLeaseRenewalsUnderDelay`.
