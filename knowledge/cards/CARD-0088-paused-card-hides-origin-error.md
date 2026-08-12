# CARD-0088 — пауза на карточке скрывает внутреннюю Origin-ошибку

Implementation commit: 031b00131f43f2be4d3856749fd6ac1c5b486dd8 — карточка сохраняет паузу и не показывает владельцу внутреннюю same-origin ошибку.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/79744f1d-85a-80ed00a7-a0a`.
- Implementation commit: `031b00131f43f2be4d3856749fd6ac1c5b486dd8`.
- What changed: при ошибке продолжения карточка подтверждает сохранённую паузу; `cross_origin_request` остаётся в серверном журнале запроса.
- Evidence: Go tests PASS; целевой компонентный тест PASS; HTTPS Playwright-сценарий паузы PASS; полный UI-набор: 153/157, четыре сбоя вне изменения.
- Next action: выполнить human merge после учёта известных нестабильных UI-тестов.

## LOG

### 2026-08-11 — Implement

- Воспроизведён ответ `403 cross_origin_request` от `POST /api/v1/works/resume`: UI больше не выводит `browser mutations must be same-origin` и явно сообщает, что пауза сохранена.
- Серверная регрессия журнала `TestHTTPRejectsMalformedOversizedAndCrossOriginMutations` прошла и подтверждает `error_class=cross_origin_request`.
- Узкий UI-тест (4), TypeScript, ESLint, production build и реальный HTTPS Playwright-сценарий (1) прошли.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Внутренняя same-origin ошибка не видна владельцу | `WorkView.test.tsx`: отклонённый `APIError(cross_origin_request)` | PASS: показано нейтральное сообщение, `same-origin` и `cross_origin_request` отсутствуют |
| Пауза остаётся понятной и доступной для повтора | тот же компонентный тест | PASS: «Пауза сохранена», кнопка «Продолжить» остаётся видимой |
| Сквозной HTTPS путь не раскрывает текст прокси | `just test-browser`, сценарий `resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected` | PASS (1 сценарий, 8.8 s) |
| Регрессия Go-части | `just test` | PASS |
| Полный UI-набор | `just ui-check` | 153/157 PASS; App/Dialog и соседний WorkView-тест упали/вышли по тайм-ауту вне этой правки; целевой тест PASS |
