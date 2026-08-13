# CARD-0122 — Ежедневный визуальный отчёт PDF

Implementation commit: 68a49e40f0cf84993206d70ff94b3bfb973fed00 — ежедневный PDF содержит проверенные снимки и сравнение метрик, а конкурентная сборка защищена токенами

## HEAD

- Status: Implemented and verified; ready for Review
- Branch: `factory/82ef0eb7-b45-42d390c6-7be`
- Implementation commit: `68a49e40f0cf84993206d70ff94b3bfb973fed00`
- What changed: долговечная служба создаёт и повторяет снимки `before`/`after`; проверенные PNG встраиваются в PDF рядом с календарными метриками «до/после».
- What changed: claim-токены, уникальные файлы, deadline, точный timezone и сверка SHA-256 закрывают гонки сборки и неоднозначное скачивание.
- Evidence: `go test -timeout 5m ./...` → PASS; web lint/typecheck/build → PASS; web suite → 174 PASS; inline-image Chromium PDF test → PASS; binary build → PASS.
- One next action: повторно передать реализацию на Review и после выпуска открыть `/reports`.

## LOG

### 2026-08-13 — Implement

Исправлены находки Review F1–F5 и риск целостности: фоновой capture-worker переводит снимки через durable states и повторяет сбой, успешная заданная стадия ставит `after`, PDF встраивает проверенные PNG и календарное сравнение двух дней. Claim-токены и уникальные имена не дают просроченному renderer перезаписать новый отчёт; download требует точный timezone и пересчитывает SHA-256. Целевые тесты покрывают снимки, повтор, `after`, DST/часовые пояса, конкурентную сборку и повреждённый PDF. Полные Go- и UI-наборы, lint, typecheck, production build, сборка бинарников и Chromium PDF-тест прошли.

### 2026-08-13 — Implement

Подключена суточная фоновая генерация отчёта за прошедший день. Строка `daily_reports` служит одновременно журналом и блокировкой от дублей; ошибки renderer становятся повторяемыми, а просроченный `running` можно безопасно забрать после сбоя. Тест автоматического старта зафиксировал один временный сбой, успешный повтор, PDF-сигнатуру и ровно одну итоговую запись. Полные Go- и web-наборы (174 UI-теста), Node PDF-тест, typecheck и production build прошли.

### 2026-08-13 — Implement

Добавлены схема хранения visual target/capture/report, блокировка claim до terminal `before`, защищённые report API, локальные capture/PDF scripts и русскоязычный экран отчётов. Обязательный тест `TestDailyVisualReportKeepsMissingBeforeHonest` сначала зафиксирован красным из-за отсутствующей реализации, затем прошёл. Полные Go- и web-наборы, typecheck, production build и отдельный Node-тест `%PDF-` зелёные.
