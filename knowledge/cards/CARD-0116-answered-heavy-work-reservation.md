Implementation commit: 5bde9d8d300d40fc89179283ac80a3619c28cfe5 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.

# CARD-0116 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: IMPLEMENTED — выпускные проверки пройдены.
Branch: `factory/d3df81f7-891-a667f566-513`.
Implementation commit: 108f65581cfced81ce241813ffbf9e10b5e33ef2 — резервированная отвеченная работа отображается в общей очереди, а очистка старых вопросов сохраняет совместимый вызов.
What changed: отвеченная тяжёлая работа сохраняет durable reservation, переживает
рестарт и получает первый безопасный слот; новые тяжёлые старты ждут.
What changed: Work показывает такой резерв в разделе «В очереди», без ложного
ожидания решения владельца; циклический вызов очистки остался однопараметрическим.
Evidence: `GOCACHE=/tmp/card0116-go-cache python3 -m unittest pilot.test_pilot` → OK (357 tests, 13 skipped); UI lint/typecheck/test/build → OK (184 tests).
Next action: влить поставку в `main`.

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

### 2026-08-15 — Implement

- Резервированная отвеченная работа возвращена в раздел «В очереди»; её причина
  ожидания остаётся видимой, но Factory больше не просит у владельца решение.
- Вызов `supersede_stale_questions` снова совместим с существующими однопараметрическими
  обработчиками; очистка снятой паузы подтверждена целевым тестом.
- Полный `pilot.test_pilot` завершился OK (357 tests, 13 skipped); UI lint,
  typecheck, 184 component tests и production build завершились успешно.
