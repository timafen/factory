# CARD-0031 — Экран «Работа»: повторный этап и нагрузка CPU

## HEAD

- Status: Implemented
- Branch: `factory/c4125b3a-ced-5d745607-977`
- Head commit: `dfe4312`
- What changed: метка «заново» теперь стоит на реально повторно запущенном текущем этапе, а не на этапах справа.
- What changed: под индикатором CPU показана связь с активными работами и занятыми слотами; явно отмечено отсутствие данных по отдельным процессам.
- Evidence: `npx vitest run src/Work.test.tsx src/Overview.test.ts` → 4 passed; `npx tsc -p tsconfig.app.json --noEmit` → passed; `npm run build` → passed; `go test ./...` → passed.
- Next action: проверить `/work` и `/` на стенде с повторным кругом работы и ненулевой нагрузкой.

## LOG

### 2026-08-08 — Implement

На базе `origin/factory-custom` исправлена семантика повторного этапа и добавлено честное пояснение показателя CPU. Добавлены два сценария повторного круга и два сценария пояснения нагрузки. Целевые тесты, TypeScript, production build и Go suite зелёные. Старый `web/src/App.test.tsx` из `main` не синхронизирован с custom-навигацией: 15 из 60 сценариев этого файла остаются базовым долгом и не относятся к CARD-0031.
