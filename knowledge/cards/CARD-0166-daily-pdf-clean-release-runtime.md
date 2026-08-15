Implementation commit: 4d01a575218e3666ffdff41d9245ad9fc55a1bef — повторный откат транзакционно восстанавливает browser-среду

# CARD-0166: ежедневный PDF после чистого штатного релиза

## HEAD

Status: Implemented and verified
Branch: `factory/db641bfe-a22-70413f54-5a3`
Implementation commit: 4d01a575218e3666ffdff41d9245ad9fc55a1bef — повторный откат транзакционно восстанавливает browser-среду
What changed: поставка перенесена на свежий `main`; повторное применение browser-поколения
получает rollback backup, а fixture проверяет идемпотентный installer и новый heartbeat.
Evidence: `FACTORY_RELEASE_TEST_TIMEOUT=60 bash ops/test-fx-factory-release.sh` → PASS;
`go test ./...` → PASS; `npm test` → 181/181 PASS;
`npm run lint` и `npm run build` → PASS; report tests → 5/5 PASS.
One next action: merge the verified branch; do not run a production release in this stage.

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

### 2026-08-14 — Implement (rebase verification)

Реализация перенесена на свежий `origin/main`; SHA реализации обновлён после
перебазирования. Installer — PASS, TypeScript — PASS, report tests — 5/5 PASS.
Полный release fixture остановился на `ui-test-fail returned 0 instead of build error 5`;
живой выпуск не выполнялся.

### 2026-08-14 — Implement

UI gate исправлен после возврата владельцем: провал второй параллельной группы
теперь явно возвращает ненулевой статус, а асинхронный release fixture включает
глубокие проверки после перехода штатного выпуска в быстрый режим.
Проверки: release fixture — PASS; TypeScript — PASS; PDF report tests — 5/5 PASS.
Боевой выпуск не запускался.

### 2026-08-15 — Implement

Поставка перебазирована на свежий `origin/main`. Конфликты объединены с новыми
гарантиями полного поколения; повторный rollback теперь резервирует browser live-state,
а fixture поддерживает повторное применение installer и монотонный heartbeat.
Проверки: release fixture — PASS; Go suite — PASS; web — 181/181, lint и build PASS;
installer — PASS; PDF report tests — 5/5 PASS. Боевой выпуск не запускался.
