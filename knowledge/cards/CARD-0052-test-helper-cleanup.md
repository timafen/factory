# CARD-0052 — Проверки не оставляют worker test-helper процессы

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/cfdc2905-e28-8208f744-d49`.
- Head commit: `70f71bb` — проверки завершают manager- и supervisor-helper.
- What changed: manager-helper получает pipe жизни родительского теста и
  завершает manager при его закрытии; crash-тест ожидает исчезновения supervisor.
- Evidence: `go test ./...` → PASS; после завершения нет процессов
  `TestWorkerManagerHelperProcess` или `TestWorkerSupervisorHelperProcess`.
- One next action: человек проверяет изменение перед слиянием.

## LOG

### 2026-08-10 — Implement

У manager test-helper был вечный `context.Background()`: при аварийном конце
родительского `go test` он мог жить дольше проверки. Pipe жизни родителя
отменяет context на EOF, а новая регрессия подтверждает штатное завершение.
Сценарий аварийной остановки теперь ждёт также исчезновения supervisor, поэтому
полная проверка не завершится, пока её helper-процессы не очищены.
