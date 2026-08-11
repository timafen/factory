# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — два review blocker закрыты, полный Verify оставлен следующему этапу.
- Branch: `factory/a4b3147f-6de-6f14159c-418`.
- Implementation commit: 98e2f854ddf5b3e8df309f6959e4a639275bfe9f — закрыты crash-окна после merge и после Popen.
- What changed: durable merge intent восстанавливает journal, delivery wait и release, когда после рестарта ветка уже в `main`.
- What changed: durable launch token позволяет новому Pilot найти и усыновить уже запущенный release wrapper без второго внешнего запуска.
- Evidence: 35 целевых Python-тестов, 12 Work UI-тестов, production build, `just check` и `just test-worker-race` прошли.
- Next action: Verify независимо повторяет полный набор и подтверждает поставку.

## LOG

### 2026-08-11 — Specification

Финальный PASS должен принадлежать успешному выпуску, а не одному merge.
Выбран устойчивый delivery wait, связанный с Verify task и поколением release;
эпики и UI используют только подтверждённый delivery receipt.

### 2026-08-11 — Implement

В исходной review-ветке merge journal, delivery wait, release receipt и
идемпотентные уведомления разделены на устойчивые шаги. Lock `rc=8`, terminal
failure и рестарты покрыты 33 Python- и 12 UI-проверками.

### 2026-08-11 — Implement

На ветке `factory/a4b3147f-6de-6f14159c-418` до внешнего `gh_merge` добавлен
durable intent: после crash и `ahead_by == 0` он создаёт пропущенный journal и
возобновляет release wait. Release wrapper получает сохранённый launch token в
argv; рестарт находит процесс в `/proc` и усыновляет его без второго `Popen`.
Регрессии моделируют обе точные crash-границы. Реализация —
`98e2f854ddf5b3e8df309f6959e4a639275bfe9f`; 35 целевых тестов, `just check`,
`just test-worker-race`, 12 UI-тестов и production build прошли.
