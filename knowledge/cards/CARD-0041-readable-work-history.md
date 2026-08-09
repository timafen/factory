# CARD-0041 — История работы простыми словами

## HEAD

- Status: Implemented — готово к повторному Review.
- Branch: `factory/67cc9c00-440-c8aef40a-3c4`.
- Head commit: `b503e1d` — реализация API, экрана и целевых проверок после rebase.
- What changed: раскрытая история работы показывает короткое русское описание
  состояния каждого этапа. Новый API не возвращает вывод, ошибки или промпт агента.
- Evidence: `go test ./internal/controlplane -run TestHTTPWorkHistory` — PASS;
  `npm test -- --run src/WorkHistory.test.tsx src/Work.test.ts` — 6/6 PASS;
  `npx tsc -p tsconfig.app.json --noEmit`, `go test ./...` и `npm run build` — PASS.
- Next action: провести повторный Review трёхточечного diff от `origin/main`.

ГОТОВО-КОГДА: файл internal/controlplane/work_history_http.go
ГОТОВО-КОГДА: файл internal/controlplane/work_history_http_test.go
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/WorkHistory.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run TestHTTPWorkHistory
ГОТОВО-КОГДА: команда cd web && npm test -- --run src/WorkHistory.test.tsx src/Work.test.ts
ГОТОВО-КОГДА: команда cd web && npx tsc -p tsconfig.app.json --noEmit

## LOG

### 2026-08-09 — Implement

Зарегистрирован ограниченный `GET /api/v1/work-history`: неизвестные задачи
пропускаются, опасные и чрезмерные запросы отклоняются, содержимое работы не
выдаётся. Экран показывает полученную сводку и сохраняет обычный статус при
отказе API. Серверные тесты и 6 целевых UI-тестов прошли; TypeScript ошибок не
нашёл.

Полный Go-набор и production-сборка прошли. Полный UI-набор: 100 тестов прошли,
три известных теста `Dialog.test.tsx` из CARD-0040 упали вне области этой задачи.
