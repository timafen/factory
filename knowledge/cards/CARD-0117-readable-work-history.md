# CARD-0041 — История работы простыми словами

## HEAD

- Status: Verified PASS — ожидает слияния человеком.
- Branch: `factory/3d94840e-ee5-afedf6ce-a0a`.
- Head commit: `d08c5ac` — проверенная реализация API, экрана и пакетной загрузки и проверки.
- What changed: раскрытая история работы показывает короткое русское описание
  состояния каждого этапа. Новый API не возвращает вывод, ошибки или промпт агента.
- Evidence: полный `go test ./...` — PASS; `npm run lint` и `npm run build` — PASS;
  в полном `npm test` — 101/104 PASS, а 3 известных отказа только в
  `Dialog.test.tsx`, вне CARD-0041. Целевой `WorkHistory.test.tsx` — 3/3 PASS.
- Next action: человеку проверить и слить ветку в `main`.

ГОТОВО-КОГДА: файл internal/controlplane/work_history_http.go
ГОТОВО-КОГДА: файл internal/controlplane/work_history_http_test.go
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/WorkHistory.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run TestHTTPWorkHistory
ГОТОВО-КОГДА: команда cd web && npm test -- --run src/WorkHistory.test.tsx src/Work.test.ts
ГОТОВО-КОГДА: команда cd web && npx tsc -p tsconfig.app.json --noEmit

## LOG

### 2026-08-09 — Verify

| Проверка | Команда или наблюдение | Результат |
| --- | --- | --- |
| Безопасная краткая история | `go test ./...`; `TestHTTPWorkHistoryReturnsSafeRussianSummary` | PASS: API возвращает только русский итог состояния, без вывода, ошибок и промпта агента. |
| Ограничения API | `TestHTTPWorkHistoryRejectsUnsafeOrUnboundedQueries` | PASS: неизвестные ID пропускаются; опасные и более 100 ID отклоняются. |
| История на экране и граница 101 | `WorkHistory.test.tsx` в полном `npm test` | PASS: 3/3, 101 задача запрошена пакетами 100 + 1 и показана. |
| Сборка и качество веб-кода | `npm run lint`; `npm run build` | PASS. |
| Полный веб-набор | `npm test` | 101/104 PASS; 3 прежних отказа `Dialog.test.tsx` вне области CARD-0041. |

### 2026-08-09 — Implement

Исправлен отказ краткой истории на обычной странице более чем из 100 задач:
экран делит идентификаторы на запросы по 100 и объединяет ответы. UI-тест
подтвердил граничный случай 101 задачи двумя запросами 100 + 1; целевые 7 тестов,
проверка типов, полный Go-набор и production-сборка прошли. В полном UI-наборе
остались три прежних отказа `Dialog.test.tsx`, не связанных с CARD-0041.

### 2026-08-09 — Implement

Зарегистрирован ограниченный `GET /api/v1/work-history`: неизвестные задачи
пропускаются, опасные и чрезмерные запросы отклоняются, содержимое работы не
выдаётся. Экран показывает полученную сводку и сохраняет обычный статус при
отказе API. Серверные тесты и 6 целевых UI-тестов прошли; TypeScript ошибок не
нашёл.

Полный Go-набор и production-сборка прошли. Полный UI-набор: 100 тестов прошли,
три известных теста `Dialog.test.tsx` из CARD-0040 упали вне области этой задачи.
