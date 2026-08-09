# CARD-0041 — История работы простыми словами

## HEAD

- Status: Implemented — готово к повторному ревью.
- Branch: `factory/7ebe82cf-c79-ad38706e-36f`.
- Head commit: `0e11f7a`.
- What changed: экран работы получает краткую историю попыток; новый API
  строит её только из номера и состояния, не читая скрытые данные.
- Evidence: `go test ./internal/controlplane -run 'TestHTTPWorkHistory' -count=1`
  → PASS, включая проверку отсутствия output, prompt, context и payload;
  `npm --prefix web test -- --run src/Work.test.ts` → 4 PASS;
  `npm --prefix web run build` → PASS.
- Next action: повторить ревью полного изменения относительно свежего `origin/main`.

ГОТОВО-КОГДА: файл internal/controlplane/work_history_http.go
ГОТОВО-КОГДА: файл internal/controlplane/work_history_http_test.go
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestHTTPWorkHistory' -count=1
ГОТОВО-КОГДА: команда npm --prefix web test -- --run src/Work.test.ts
ГОТОВО-КОГДА: команда npm --prefix web run build

## LOG

### 2026-08-09 — Implement

Добавлен и зарегистрирован `GET /api/v1/work-history`. Ответ содержит только
человекочитаемые фразы о ходе попыток и идентификатор задачи; SQL-запрос намеренно
не выбирает prompt, context, result, error или payload. Целевые HTTP-тесты
подкладывают секреты в результат, ошибку и событие и подтверждают, что ответ их
не содержит. Экран подключён к работающему маршруту, его тесты и сборка проходят.
