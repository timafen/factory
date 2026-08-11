# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — оба blocker review закрыты restart-cycle регрессиями.
- Branch: `factory/7c7c4809-d14-20c91eac-0bf`.
- Implementation commit: 9485189cf1b6d2846a296823388bc1d422eb3ae9 — восстановление merge intent и разделение reservation/successor release.
- What changed: durable intent восстанавливается в начале `cycle()` даже при `processed`; journal, wait и generation 1 сохраняются за два цикла.
- What changed: `successor_queued` отличает следующий выпуск от завершённого wrapper с launch token, поэтому generation 2 не запускается.
- Evidence: 2 новых полных restart-cycle теста и полный `python3 -m unittest pilot.test_pilot` прошли; `just build` прошёл.
- Next action: Verify повторяет полный набор проверок в среде без лимита длительных worker/UI задач.

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

### 2026-08-11 — Implement

В `cycle()` добавлено восстановление durable merge intent до фильтра `processed`;
первый restart создаёт journal, delivery wait и generation 1, второй их не дублирует.
Для release разделены reservation и queued successor: status завершённого wrapper
с launch token не запускает generation 2. Реализация —
`9485189cf1b6d2846a296823388bc1d422eb3ae9`; два restart-cycle теста, весь
`pilot.test_pilot` и `just build` прошли. Длительные worker/UI проверки требуют среды без лимита исполнителя.
