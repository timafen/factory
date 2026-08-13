Implementation commit: c1c48599ef8e572080e15170da202c347b68a416 — проверка экрана Work использует независимую завершённую задачу

# CARD-0068 — Стабильная браузерная проверка «Сделано» на Work

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/fff62fc5-713-e91bcf4e-661`.
- Implementation commit: c1c48599ef8e572080e15170da202c347b68a416 — сквозная проверка экрана Work больше не зависит от предыдущего сценария.
- What changed: сценарий сверяет завершённую задачу общей фикстуры в разделе «Сделано» и после открытия архива.
- Evidence: чистая установка зависимостей; полный `npm run lint && npm run typecheck && npm test && npm run test:browser`; отдельный Playwright-сценарий Work — 1 passed.
- One next action: владельцу проверить поставку и влить её в `main`.

## LOG

### 2026-08-11 — Implement

Экранная регрессия опиралась на задачу, которую создавал другой тест, поэтому одиночный запуск Work мог не увидеть её в активной группе. Проверка теперь использует самостоятельную успешную API-фикстуру и подтверждает её видимость до и после открытия архива. Целевой браузерный сценарий, production build, lint и 145 unit-тестов завершились успешно.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Проверка Work не зависит от задачи соседнего сценария | просмотр реализации `c1c48599ef8e572080e15170da202c347b68a416` | сценарий использует самостоятельную успешную фикстуру `Ship the stable API client` |
| Завершённая задача видна в «Сделано» и архиве | `npx playwright test e2e/control-plane.spec.ts --grep 'renders grouped work and saves the desktop Work view' --reporter=line` | 1 passed; оба отображения подтверждены браузером |
| Смежные web-регрессии отсутствуют | `npm ci`; `npm run lint && npm run typecheck && npm test && npm run test:browser` | все этапы завершились успешно |
| Поставка и карточка согласованы | `git merge-base --is-ancestor` и `git diff --name-only origin/main...HEAD` | implementation-коммит — предок, меняет E2E-код; в diff только карточка и сценарий |
