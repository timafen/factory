Implementation commit: e941d725b099e16bc16e633d9b8983189c95cf69 — основной цикл изолирует артефакты, ветки и повторы по work_id

## HEAD

Status: Implemented
Branch: factory/c76d2381-1db-dfd0f842-603
Implementation commit: e941d725b099e16bc16e633d9b8983189c95cf69
What changed: основной цикл передаёт work_id в implementation/delivery artifacts, Review/Verify/merge и созданные следующие задачи.
What changed: остановка, дубликаты, попытки и возвраты ограничены work_id; title остаётся только legacy fallback без provenance.
Evidence: `python3 -m unittest -q pilot.test_pilot.SameTitlePlanEpicBudgetIsolationTests` → 5 OK, включая две одноимённые реализации с разными Review-ветками.
One next action: повторить Review поставки.

## LOG

### 2026-08-11 — Implement

Перенесена изоляция по `work_id` на свежий `origin/main` с сохранением новой логики Pilot. Все 218 Pilot-тестов прошли; общий `just check` дошёл до независимых Go-тестов и остановился по их пятиминутному timeout вне области изменения.

### 2026-08-12 — Implement

Доведён основной cycle: durable `work_id` сопровождает артефакт реализации, выбранную ветку доставки, переходы Review/Verify/merge, проверки остановки, дубликатов и лимитов попыток. Добавлен полный сценарий двух одноимённых Implement-задач: каждая передаёт в Review только свою ветку, а бюджетный стоп одной не блокирует другую. Целевой набор `SameTitlePlanEpicBudgetIsolationTests` прошёл: 5 OK.
