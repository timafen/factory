Implementation commit: 16eab48e1fe2a20ff2ae01bdff23f070fb51c251 — durable reservation покрыт backend-проверками восстановления, FIFO, приоритета и освобождения после запуска.

# CARD-0116 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: IMPLEMENTED — готово к повторной проверке выпуска.
Branch: `factory/e8691177-e88-17abb425-6e4`.
Implementation commit: 16eab48e1fe2a20ff2ae01bdff23f070fb51c251 — durable reservation покрыт backend-проверками восстановления, FIFO, приоритета и освобождения после запуска.
What changed: ответ на тяжёлый этап сохраняет резерв в вопросе, переживает
рестарт и получает первый безопасный слот; новые тяжёлые старты ждут.
What changed: backend-проверки подтверждают восстановление из файлов, FIFO
нескольких ответов, блокировку конкурирующего запуска и снятие резерва.
Evidence: `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` → OK (8 tests).
Next action: Review повторно проверяет поставку перед Verify; в `main` не вливать до PASS.

## LOG

### 2026-08-14 — Specification

- Подтверждён источник готовой поставки и критерии: durable reservation,
  приоритет перед новыми тяжёлыми работами и видимый владельцу статус.

### 2026-08-14 — Implement

- Перенесена поставка на свежий `main`, разрешено пересечение с новым
  приоритетом продолжений без потери его учёта по work id.
- `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` завершился OK
  (3 tests). UI-команда не стартовала: в worktree отсутствуют пакеты `vitest`
  и `@vitejs/plugin-react`.

### 2026-08-14 — Implement

- Добавлены backend-проверки durable reservation: восстановление из файлов,
  FIFO нескольких ответов, запрет нового тяжёлого старта, приоритет владельца
  и снятие резерва после запуска продолжения.
- `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` завершился OK
  (8 tests).
