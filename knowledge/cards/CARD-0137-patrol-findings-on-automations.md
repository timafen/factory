# CARD-0137 — Патрули и находки на экране «Автоматизации»

## HEAD

Status: Implemented
Branch: factory/99c742b9-c4e-570e6c2f-932
Implementation commit: adbe52c3bc17e0d3db59cc4180336cb8bed6dc32 — патрульные задачи скрываются из «Работа», а результаты запусков показываются в «Автоматизациях»
What changed: Tasks получают устойчивый `work_class` по фактам scheduled Automation; occurrence проецирует последнюю попытку, включая result/error. UI фильтрует patrol и показывает находки/итог.
Evidence: `go test ./...` — PASS; `cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx` — 17 PASS; typecheck/lint/build — PASS.
Next action: Verify на стенде открыть `/work` и `/automations/<id>` у патруля с успешным, неуспешным и пустым запуском.

## LOG

### 2026-08-14 — Implement

Реализован перенос патрульных задач из экрана «Работа» в историю запусков Automation.
Добавлены проекция последней попытки, разбор канонических `НАХОДКА:` и нейтральный итог без результата.
Целевые web-тесты: 17 passed; полный Go-набор и web typecheck/lint/build прошли.
