# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 7fa837290acb91b1eb424b7fc81931eb0ec8396a — ежедневный PDF и его проверка ошибки БД готовы к Review

## HEAD

- Status: IMPLEMENTED / VERIFY PASS
- Branch: `factory/e90e2bce-f51-76fd19d6-72d`
- Implementation commit: `7fa837290acb91b1eb424b7fc81931eb0ec8396a`
- What changed: ежедневный PDF сохраняет проверенные снимки и метрики «до/после»; Chromium запускается только через изолирующий launcher с sandbox и allowlist.
- What changed: тест ошибки БД владеет своим хранилищем, поэтому проверяет HTTP 5xx без ложного сбоя повторного cleanup.
- Evidence: регрессия закрытой БД 5/5, Node PDF 2/2, web 179/179, полный `go test -timeout 5m ./...`, lint/typecheck/build и browser shell → PASS.
- One next action: провести Review поставки и слить ветку при PASS.

## LOG

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
