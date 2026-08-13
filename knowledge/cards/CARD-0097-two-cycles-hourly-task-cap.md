# CARD-0097 — Два цикла ограничены десятью задачами в час

Implementation commit: 75410ad75705be54e1f4271e468c42a0aac8c015 — Pilot ждёт следующей допустимой попытки, а лимит проверен конкурентно.

## HEAD

- Status: Implement + Test — готово.
- Branch: `factory/d329a8f9-09f-c8e8d9e4-835`.
- Implementation commit: `75410ad75705be54e1f4271e468c42a0aac8c015` — Pilot не вызывает создание до сохранённого срока, а control plane проверен при гонке.
- What changed: сохраняется `hourly_cap_retry_at`; следующий цикл пропускается, а после срока задача создаётся.
- What changed: добавлен `TestCreateTaskHourlyTaskCapConcurrent` с двумя горутинами и пределом в 10 задач.
- Evidence: `go test ./internal/controlplane -run 'TestCreateTaskHourlyTaskCap(ReplayAndWindow|Concurrent)$'` → PASS.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanAutostartTest` → PASS (17 тестов).
- Next action: Передать ветку на Verify.

## LOG

### 2026-08-12 — Implement

После ответа владельца Pilot сохраняет полный час до следующей попытки и не
вызывает `create_task` в следующем цикле до этого срока. Добавлен настоящий
конкурентный тест с двумя горутинами: при девяти уже созданных задачах проходит
ровно одна попытка, а в окне остаётся не более десяти. Целевые Go- и Pilot-
тесты прошли.

### 2026-08-12 — Implement

Исправлены две ссылки в спецификации: обязательная команда теперь использует
существующий `PlanAutostartTest`. Целевая Go-проверка и 17 Pilot-тестов прошли
одной командой без `AttributeError`.

### 2026-08-12 — Implement

Добавлены durable-метка автоматической задачи, атомарная проверка скользящего часа и миграция 028. Целевой Go-тест подтверждает границу, replay, ручную задачу и освобождение окна; Pilot-тест подтверждает defer и одно уведомление.

## Статус

Specification — готова к Implement + Test.

## Суть работы

Два цикла Factory могут одновременно проходить несколько веток создания
продолжений, а текущие `day_task_cap` и `_active_work_tasks` не задают общий
скользящий часовой предел. Следующий этап должен добавить единый атомарный
контроль в control plane: не более 10 новых автоматических задач за 60 минут,
идемпотентный replay без расхода квоты и отложенный handoff в Pilot.

## Область

- `internal/controlplane/store.go` и миграция для durable почасового окна;
- `pilot/pilot.py` для понятного defer без повторной постановки;
- целевые тесты control plane и Pilot;
- UI и продуктовые экраны не менять.

## Проверки следующего этапа

- десять созданий проходят, одиннадцатое получает `hourly_task_cap`;
- две конкурентные транзакции не превышают лимит;
- replay того же `request_key` не расходует квоту;
- после истечения 60 минут создаётся ровно один следующий этап;
- `go test ./internal/controlplane` и `python3 -m unittest pilot.test_pilot`.

## Контекст поставки

Свежий remote default branch: `2a6eb6046f5a595e5156a4ec030e0a1aa2f6e11`.
Удалённой ветки текущего кандидата на момент Specification нет; локальный
кандидат совпадает с базой. Карточка создана как `CARD-0097`, поскольку этот
номер отсутствует в свежем `origin/main`.
