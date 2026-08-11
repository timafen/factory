# CARD-0060 — Завершённая задача видна на экране Work

## HEAD

- Status: Implemented.
- Branch: `agent/finish-card0060`.
- Implementation commit: b14b9b25675cb12ff249157572c86240758a1fa2 — успешная отдельная задача показывается в «Сделано».
- What changed: последняя успешная попытка без pipeline-вердикта получает статус «работа завершена»; отменённые, неуспешные и возвращённые на доработку работы остаются в истории.
- Evidence: `cd web && npm test -- --run src/Work.test.ts` — 10 tests passed; `cd web && npm run typecheck` — passed.
- Next action: на Verify запустить полный `just test-browser`.

## LOG

### 2026-08-10 — Implement

Реализован показ обычной успешно завершённой задачи в разделе «Сделано» Work и добавлены unit- и сквозная регрессии. Целевой Vitest прошёл (10 тестов), TypeScript-проверка прошла. Одиночный Playwright-сценарий требует созданной предыдущим serial-сценарием задачи; связанный прогон остаётся финальной сквозной проверкой.
