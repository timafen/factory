Implementation commit: 102bfad95939d07c6dbc61e223b11de9d42e4b35 — `route_question()` считает попытки по полной строгой истории задач

# CARD-0162 — Стоп-кран считает всю историю попыток

## HEAD

Status: Implement + Test — готово к Review.

Branch: `factory/9e46698e-194-b0c86ea3-0bd`.

Implementation commit: 102bfad95939d07c6dbc61e223b11de9d42e4b35 — `route_question()` считает попытки по полной строгой истории задач.

What changed: перед нетехническими порогами `route_question()` читает полную
постраничную историю, удаляет дубли `task.id` и считает попытки той же работы по
`work_id`; неполная история безопасно возвращает терминальную задачу в обработку.

Evidence: `python3 -m unittest -v pilot.test_pilot.RouteQuestionCompleteAttemptCountTests pilot.test_pilot.DiagnosisRepairTests` — 22 tests, OK.

One next action: проверить поставку в Review на свежем `main`.

## LOG

### 2026-08-15 — Implement

После устранения конфликта с актуальным `main` реализация возвращена отдельным
кодовым коммитом. Строгая история защищает диагностику, лимит стадии и стоп-кран
от неполного счётчика; целевые 22 теста проходят.
