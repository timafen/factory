# CARD-0097 — Два цикла ограничены десятью задачами в час

Implementation commit: f412f7743b3e334f097a5d880b4cc0a7614f26b7 — контрольная плоскость ограничивает создание автоматических задач десятью за скользящий час.

## HEAD

- Status: Implement + Test — готово.
- Branch: `factory/07095b28-30a-24d34201-e77`.
- Implementation commit: `f412f7743b3e334f097a5d880b4cc0a7614f26b7` — общий атомарный почасовой лимит и отложенный Pilot handoff.
- What changed: SQLite учитывает только `[auto]` задачи по серверному времени; replay и ручные задачи не расходуют окно. Pilot сохраняет карточку в плане и уведомляет один раз.
- Evidence: `go test ./internal/controlplane -run 'TestCreateTaskHourlyTaskCap' -count=1` → PASS; `python3 -m unittest pilot.test_pilot -q` → 242 tests PASS.
- Next action: Review проверить конкурентный доступ к SQLite и HTTP-контракт `hourly_task_cap`.

## LOG

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
