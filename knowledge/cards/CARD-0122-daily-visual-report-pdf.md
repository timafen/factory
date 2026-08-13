# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 270854f9d720299b94411f78f6fb310cabf48d17 — снимки PDF ограничены изолированным Chromium и разрешёнными хостами, а сбои URL, recovery mode и БД обработаны безопасно

## HEAD

- Status: Implemented and verified; ready for Review
- Branch: `factory/28591ece-f5d-5baef51e-932`
- Implementation commit: `270854f9d720299b94411f78f6fb310cabf48d17`
- What changed: ежедневный PDF сохраняет проверенные снимки и метрики «до/после»; Chromium запускается только через изолирующий launcher с sandbox и allowlist.
- What changed: malformed URL отклоняется без panic, recovery mode не создаёт report storage, ошибка чтения БД возвращает 5xx.
- Evidence: `go test ./internal/controlplane ./cmd/factory-server` → PASS; TypeScript/build/lint/UI/Node/browser installer → PASS.
- One next action: передать исправленную реализацию на Review и после выпуска открыть `/reports`.

## LOG

### 2026-08-13 — Implement

Закрыты M1–M3 и minor из остановленного Review: capture использует только абсолютный изолирующий launcher, `chromiumSandbox: true` и список разрешённых хостов; URL разбирается до обращения к hostname; report runtime инициализируется после recovery mode; SQL-сбой скачивания возвращает 5xx. Целевые Go-, UI-, Node- и browser installer тесты, TypeScript, lint и production build прошли.

### 2026-08-13 — Implement

Исправлены находки Review F1–F5 и риск целостности: фоновой capture-worker переводит снимки через durable states и повторяет сбой, успешная заданная стадия ставит `after`, PDF встраивает проверенные PNG и календарное сравнение двух дней. Claim-токены и уникальные имена не дают просроченному renderer перезаписать новый отчёт; download требует точный timezone и пересчитывает SHA-256. Целевые тесты покрывают снимки, повтор, `after`, DST/часовые пояса, конкурентную сборку и повреждённый PDF. Полные Go- и UI-наборы, lint, typecheck, production build, сборка бинарников и Chromium PDF-тест прошли.

### 2026-08-13 — Implement

Подключена суточная фоновая генерация отчёта за прошедший день. Строка `daily_reports` служит одновременно журналом и блокировкой от дублей; ошибки renderer становятся повторяемыми, а просроченный `running` можно безопасно забрать после сбоя. Тест автоматического старта зафиксировал один временный сбой, успешный повтор, PDF-сигнатуру и ровно одну итоговую запись. Полные Go- и web-наборы (174 UI-теста), Node PDF-тест, typecheck и production build прошли.

### 2026-08-13 — Implement

Добавлены схема хранения visual target/capture/report, блокировка claim до terminal `before`, защищённые report API, локальные capture/PDF scripts и русскоязычный экран отчётов. Обязательный тест `TestDailyVisualReportKeepsMissingBeforeHonest` сначала зафиксирован красным из-за отсутствующей реализации, затем прошёл. Полные Go- и web-наборы, typecheck, production build и отдельный Node-тест `%PDF-` зелёные.
