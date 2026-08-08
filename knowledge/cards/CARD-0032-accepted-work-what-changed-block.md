# CARD-0032 — Принятая работа: блок «Что изменилось» вместо пустоты

## HEAD

- Status: Implemented — готово к ревью.
- Branch: `factory/50ff8605-428-478cd5f2-921`.
- Head commit: смотри `git rev-parse --short HEAD` после этого коммита.
- Что изменилось: страница принятой задачи показывает человеческую часть Verify-отчёта; если её нет — результат последней попытки, вместо пустого «Итог».
- Что изменилось: служебные строки отчёта (`BRANCH:`, `HEAD:`, `PUSHED:`, `TRY:`, одиночные `PASS`/`APPROVE`/`REQUEST CHANGES`) скрываются из текста; неизвестные строки остаются видимыми.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` → PASS; `npx vitest run src/Summary.test.tsx` → 4/4 PASS; `npx eslint src/Summary.tsx src/Summary.test.tsx src/whatChanged.ts` → PASS; `npm run build` → PASS.
- One next action: открыть принятую задачу в `/tasks/<task-id>` и подтвердить блок на реальном отчёте.

## LOG

### 2026-08-08 — Implement

Реализация уже существовала на ветке `factory/37777e21-a1a-58584fc1-4ca` (карточка `CARD-0031.md` там же) — три предыдущих круга конвейера отчитывались о готовности, но фактический код так и не попал на назначенную конвейером ветку и не был запушен под тем именем, которое ожидал Verify. Работа не запускалась заново: тот же код (`web/src/whatChanged.ts`, изменения `web/src/Summary.tsx`, `web/src/Summary.test.tsx`) перенесён на актуальную назначенную ветку `factory/50ff8605-428-478cd5f2-921` от её текущего состояния (main давно влит). Номер карточки — `CARD-0032`, так как `CARD-0031` на этой ветке уже занята другой темой (экран «Работа», доработка и CPU).

Целевые 4 теста прошли, TypeScript и eslint изменённых файлов чистые, production build прошёл. Полный `vitest run`: 71 passed, 15 известных падений — все в неизменённом `src/App.test.tsx`, не связаны с этим diff. `go build ./...` — чисто (Go-код не менялся).

Ветка запушена на `origin` и подтверждена через `git ls-remote`.
