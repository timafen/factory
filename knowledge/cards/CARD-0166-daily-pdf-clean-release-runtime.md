Implementation commit: 031e6c9d63d3c174cce7067cd758979b664285bb — служебный пользователь получает доступ к постоянному Chromium runtime, а сбой до journal возвращает live-state.

# CARD-0166: ежедневный PDF после чистого штатного релиза

## HEAD

Status: Implemented — awaiting Review
Branch: `factory/77de079d-588-9c3552f3-2ed`
Implementation commit: `031e6c9d63d3c174cce7067cd758979b664285bb`
What changed: generation parents и Chromium payload доступны группе служебного
пользователя без права записи; installer проверен отдельной service identity.
Cleanup возвращает browser live-state после любого сбоя между installer и prepared journal.
Evidence: `bash ops/test-install-server-browser.sh` → PASS; отдельная service identity
загружает Playwright из постоянного payload. `bash ops/test-fx-factory-release.sh` → PASS;
сбой после browser smoke восстанавливает live-state, не создаёт journal и не трогает службы.
One next action: провести Review доступа service user и раннего rollback-контракта.

## LOG

### 2026-08-14 — Specification

Подтверждена причина ручного восстановления: встроенному PDF renderer нужен
`playwright`, но штатный выпуск оставляет `npm ci` только во временном checkout.
Спецификация требует устанавливать и проверять browser runtime до остановки служб,
публиковать его атомарно вместе с выпуском и возвращать при rollback. Отдельный тест
должен получить `%PDF-` после удаления checkout на fixture без `/opt/factory`.
Продуктовый код и UI на этапе Specification не изменялись.

### 2026-08-14 — Уточнение критерия готовности

В спецификации явно добавлен проверяемый результат: целевая команда должна
воспроизвести чистый релиз, удалить build checkout и получить `%PDF-`, не
публикуя browser runtime при ошибке подготовки. В конце спецификации отдельно
зафиксированы все файлы реализации и обязательная команда с нулевым кодом выхода.

### 2026-08-14 — Implement

Штатный релиз получил постоянное browser-поколение с pinned Playwright/Chromium,
readiness и PDF smoke до остановки служб. `browser-current` переключается вместе с
release generation, а сохранённый live-state возвращает launcher/profile при позднем
откате. Production renderer/capture используют только `FACTORY_BROWSER_PAYLOAD`.
Проверки: release fixture — PASS; installer — PASS; Node — 5/5; Go target — PASS;
web — 180/180 и production build PASS.

### 2026-08-14 — Implement

Исправлены замечания Review: runtime Chromium и все его родители открыты группе
служебного пользователя только на чтение/проход, а отдельная service identity
загружает Playwright из опубликованного поколения. Cleanup вооружён сразу после
installer и возвращает browser live-state при сбое до `prepared` journal.
Проверки: `bash ops/test-install-server-browser.sh` — PASS;
`bash ops/test-fx-factory-release.sh` — PASS, включая сбой после browser smoke.
