# CARD-0088 — пауза на карточке скрывает внутреннюю Origin-ошибку

Implementation commit: 9709323473c4063ab3abd81da89fc72bfa853fa3 — карточка сохраняет паузу и не показывает владельцу внутреннюю same-origin ошибку.

## HEAD

- Status: Implemented and targeted checks PASS.
- Branch: `factory/0cfa2fba-b2f-e9e06471-894`.
- Implementation commit: `9709323473c4063ab3abd81da89fc72bfa853fa3`.
- What changed: при ошибке продолжения карточка подтверждает сохранённую паузу; `cross_origin_request` остаётся в серверном журнале запроса.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` → PASS; `WorkView.test.tsx` → 4 PASS; целевой HTTPS Playwright → 1 PASS; production build и lint → PASS.
- Next action: проверить изменение на `/work` после публикации ветки.

## LOG

### 2026-08-11 — Implement

- Воспроизведён ответ `403 cross_origin_request` от `POST /api/v1/works/resume`: UI больше не выводит `browser mutations must be same-origin` и явно сообщает, что пауза сохранена.
- Серверная регрессия журнала `TestHTTPRejectsMalformedOversizedAndCrossOriginMutations` прошла и подтверждает `error_class=cross_origin_request`.
- Узкий UI-тест (4), TypeScript, ESLint, production build и реальный HTTPS Playwright-сценарий (1) прошли.
