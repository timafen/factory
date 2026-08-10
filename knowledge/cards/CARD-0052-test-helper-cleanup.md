# CARD-0052 — Проверки не оставляют worker test-helper процессы

## HEAD

- Status: Implemented PASS — awaiting review.
- Branch: `factory/2d4b6ee0-c6e-1ab21fde-4f9`.
- Head commit: `e53dcb4` — ожидание manager-helper ограничено и безопасно очищается.
- What changed: manager-helper получает pipe жизни родительского теста и
  завершает manager при его закрытии; `Wait` выполняется в goroutine с таймаутом,
  а cleanup после таймаута убивает и освобождает дочерний процесс.
- Evidence: целевые тесты → PASS; `go test -timeout 5m ./...` → PASS;
  `go build ./...` → PASS; постоянных manager- или supervisor-helper не осталось.
- One next action: ревью проверяет ограниченный timeout и cleanup теста.

## LOG

### 2026-08-10 — Implement

У manager test-helper был вечный `context.Background()`: при аварийном конце
родительского `go test` он мог жить дольше проверки. Pipe жизни родителя
отменяет context на EOF, а новая регрессия подтверждает штатное завершение.
Сценарий аварийной остановки теперь ждёт также исчезновения supervisor, поэтому
полная проверка не завершится, пока её helper-процессы не очищены.

### 2026-08-10 — Implement

После ревью прямой `command.Wait()` перенесён в goroutine с пятисекундным
таймаутом. При истечении таймаута cleanup закрывает lifetime pipe, убивает
manager-helper и забирает результат `Wait`, поэтому сама регрессия не зависает
и не оставляет дочерний процесс. Целевые тесты, полный Go-набор и сборка прошли.
