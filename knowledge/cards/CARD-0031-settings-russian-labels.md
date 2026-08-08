# CARD-0031 — Русские подписи экрана «Настройки»

## HEAD

Status: READY — реализация и целевые проверки завершены.
Branch: `factory/1bb03588-5a5-b4f6174f-772`.
Head commit: `58758ab`.
What changed: все поля `PilotSettings` распределены по четырём русским разделам и получили понятные пояснения; технические значения оставлены без перевода.
Evidence: `npx vitest run src/Settings.test.tsx` — 4/4 PASS; `npx playwright test -g 'edits pilot settings from the Settings screen'` — 1/1 PASS; `npx tsc -p tsconfig.app.json --noEmit` и `npm run build` — PASS.
One next action: после слияния открыть `/settings` и подтвердить итоговый вид на рабочем стенде.

## LOG

### 2026-08-08 — Implement

Экран получил четыре русских раздела, русские подписи и пояснение к каждому полю, включая маршруты, бюджеты и строки цепочки моделей. Технические значения этапов, уровней сложности, worker ID, CLI, моделей и провайдеров не переводятся. Целевой Vitest прошёл 4/4, браузерный сценарий на ширине 1440 px — 1/1, TypeScript и production build — PASS. Общий Vitest остаётся красным на 15 старых ожиданиях англоязычного интерфейса в `App.test.tsx`, не связанных с экраном настроек; общий ESLint также имеет 11 существующих ошибок вне изменённых файлов, а ESLint изменённых файлов проходит.
