Implementation commit: 5bde9d8d300d40fc89179283ac80a3619c28cfe5 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.

# CARD-0116 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: IMPLEMENTED — готово к проверке выпуска.
Branch: `factory/29cb07e5-6c1-de1548c8-bc2`.
Implementation commit: 5bde9d8d300d40fc89179283ac80a3619c28cfe5 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.
What changed: ответ на тяжёлый этап сохраняет резерв в вопросе, переживает
рестарт и получает первый безопасный слот; новые тяжёлые старты ждут.
What changed: Answer, Work и Overview показывают принятое решение и честную
причину ожидания без нового badge открытых вопросов.
Evidence: `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` → OK (3 tests).
Next action: Verify должен установить web-зависимости, прогнать три UI-теста и browser-проверку.

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
