# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 22ca069ba4e13595f19dc0ce0f1bc3a26089bbb6 — ежедневный PDF сохраняет снимки и метрики, а Basic Auth не уходит на чужой origin

## HEAD

- Status: BLOCKED — браузерный E2E не запускается: обязательная проверка report runtime завершает Go-сервер до старта.
- Branch: `factory/bdc398e9-c14-fa2bde2b-9df`
- Implementation commit: `22ca069ba4e13595f19dc0ce0f1bc3a26089bbb6`
- What changed: восстановлена полная реализация ежедневного PDF со снимками «до/после» и сравнительными метриками.
- What changed: оба capture-скрипта ограничивают credentials origin `https://factory.timafen.com`; чужой challenge не получает `Authorization`.
- Evidence: `go test -timeout 5m ./...` → PASS; `npm test` → 16 файлов, 174 теста PASS; Node report tests → 4 PASS, 2 SKIP без launcher.
- Evidence: installer, lint, typecheck, tooling, launcher и production build → PASS; `npm run test:browser` → FAIL до Playwright из-за отсутствующего обязательного browser runtime.
- One next action: снабдить browser E2E fixture тестовым report runtime/launcher и повторить `npm run test:browser` вместе с живыми Chromium-сценариями отчёта.

## LOG

### 2026-08-13 — Implement

Исправлены четыре блокера повторной проверки: снимок «до» не открывает задачу при `missing`, поздний «после» пересобирает PDF исходной даты, startup-probe реально запускает Chromium и рендерит страницу. Для точного Factory-host capture создаёт отдельный Basic Auth context, а остальные разрешённые хосты credentials не получают. Полный Go-набор, UI test/lint/typecheck/build и Node-тест защищённого capture прошли; два сценария с установленным Chromium пропущены, поскольку launcher отсутствует в worker-контейнере.

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

### 2026-08-13 — Implement

Работа заново собрана от свежего `main` без посторонних файлов. В обоих capture-скриптах Basic Auth ограничен точным Factory-origin; автоматический redirect/challenge-тест подтвердил, что чужой HTTP-origin не получает `Authorization`. Полные Go- и UI-наборы, installer, lint, typecheck и production build прошли; два сценария живого Chromium пропущены из-за отсутствующего launcher.

### 2026-08-13 — Verify

Pinned comparison: `d98c9b10c72add76401f216a770da0994f73fe5f...1dc38179fd91a4459bf34dc474a7c3f47cecd7d5`.

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Ежедневный PDF, снимки «до/после», метрики и повторная сборка | `go test -timeout 5m ./...`; `node --test report/report.test.mjs` | PASS: все Go-пакеты зелёные; Node 4 PASS, renderer/capture с настоящим Chromium — 2 SKIP без launcher. |
| UI отчётов и API скачивания | `just ui-check`; Go-тесты report API | PASS: lint/typecheck, 16 файлов и 174 UI-теста; выбор timezone и SHA-256 целостность покрыты. |
| Sandbox, allowlist и production-сборка | `ops/test-install-server-browser.sh`; `just build`; tooling/launcher suites | PASS: installer проверил firewall, sandbox, allowlist и rollback; три бинарника собраны. |
| Смежный browser E2E | `npm run test:browser` | BLOCKED: новый startup-check завершил Go-сервер из-за отсутствующего `/usr/local/libexec/factory/browser-runtime/package.json`; Playwright не стартовал. |
| Живой `/reports` | HTTP-проверка production/staging | BLOCKED: production отвечает 401 без доступных credentials, staging — 404; launcher и `sudo -n` недоступны. |
| Общая статика | `just check` | Базовый долг вне diff: SA4000 в `internal/worker/attempt_lifecycle_test.go:31`; остальные независимые части набора запущены отдельно и прошли. |
