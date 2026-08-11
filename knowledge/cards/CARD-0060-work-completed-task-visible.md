# CARD-0060 — Завершённая задача видна на экране Work

## HEAD

- Status: Implemented.
- Branch: `factory/5c775f67-08d-fe2b830f-afa`.
- Implementation commit: 65d1675d0c3e94bcfbc111ec0b2aace9f2866bc2 — успешная отдельная задача показывается в «Сделано».
- What changed: последняя успешная попытка без pipeline-вердикта получает статус «работа завершена»; отменённые, неуспешные и возвращённые на доработку работы остаются в истории.
- Evidence: `cd web && npm test -- --run src/Work.test.ts` — 10 tests passed; `cd web && npm run typecheck` — passed.
- Next action: на Verify запустить полный `just test-browser`.

## LOG

### 2026-08-10 — Implement

Реализован показ обычной успешно завершённой задачи в разделе «Сделано» Work и добавлены unit- и сквозная регрессии. Целевой Vitest прошёл (10 тестов), TypeScript-проверка прошла. Одиночный Playwright-сценарий требует созданной предыдущим serial-сценарием задачи; связанный прогон остаётся финальной сквозной проверкой.
