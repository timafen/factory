Implementation commit: 455578a90a4762848c8929f79488babd55af8684 — штатный релиз публикует постоянное browser-поколение и сохраняет ежедневный PDF после удаления checkout.

# CARD-0166: ежедневный PDF после чистого штатного релиза

## HEAD

Status: Implemented — awaiting Review
Branch: `factory/4b9a661a-bef-7825bbe2-aec`
Implementation commit: `455578a90a4762848c8929f79488babd55af8684`
What changed: релиз готовит Playwright/Chromium и PDF smoke до остановки служб,
хранит runtime в поколении и атомарно выбирает его через `browser-current`.
Renderer/capture больше не читают checkout; поздний rollback возвращает browser state.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS; clean fixture после удаления
checkout получила `%PDF-`, а installer failure не публиковала runtime и не трогала службы.
Evidence: installer → PASS; Node 5/5; Go target → PASS; web tests 180/180; build → PASS.
One next action: провести Review коммита реализации и release/rollback-контракта.

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
