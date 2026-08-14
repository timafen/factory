Implementation commit: c0cda710ef33c884ace560cdc6451411a1cd2a36 — экранная проверка durable reservation следует фактическому статусу ожидания исполнителя.

# CARD-0116 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: IMPLEMENTED — готово к повторной проверке выпуска.
Branch: `factory/e8691177-e88-17abb425-6e4`.
Implementation commit: c0cda710ef33c884ace560cdc6451411a1cd2a36 — экранная проверка durable reservation следует фактическому статусу ожидания исполнителя.
What changed: ответ на тяжёлый этап сохраняет резерв в вопросе, переживает
рестарт и получает первый безопасный слот; новые тяжёлые старты ждут.
What changed: backend-проверки подтверждают восстановление из файлов, FIFO
нескольких ответов, блокировку конкурирующего запуска и снятие резерва.
What changed: проверка экрана работы использует видимое название раздела
«Ожидают исполнителя» для отвеченной тяжёлой работы.
Evidence: backend (8), экран работы (8), lint и build → OK.
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

### 2026-08-14 — Implement

- Экранная проверка резерва синхронизирована с видимым владельцу разделом
  «Ожидают исполнителя», а не с устаревшим названием очереди.
- `npm --prefix web test -- src/WorkView.test.tsx` завершился OK (8 tests);
  `npm --prefix web run lint` и `npm --prefix web run build` завершились OK.
