Implementation commit: 1fdfd5db906209ff76d1f032baea1679e94b55c8 — `route_question()` считает попытки по полной строгой истории задач

# CARD-0162 — Стоп-кран считает всю историю попыток

## HEAD

Status: Implement + Test — готово к Review.

Branch: `factory/29cf5ac0-17a-ab697f9e-639`.

Implementation commit: `1fdfd5db906209ff76d1f032baea1679e94b55c8` — `route_question()` считает попытки по полной строгой истории задач.

What changed: перед всеми нетехническими порогами `route_question()` получает
полную постраничную историю, дедуплицирует `task.id` и считает попытки той же
работы по `work_id` (с прежним legacy fallback). Неполная история снимает
терминальную задачу с `processed` без автоответа, паузы, вопроса или уведомления.

Evidence: `python3 -m unittest -v pilot.test_pilot.RouteQuestionCompleteAttemptCountTests` — 5 passed;
целевые `RouteQuestionCompleteAttemptCountTests` покрывают вторую страницу,
разные `work_id`, дубль, повтор cursor, ошибку API и нулевой режим ворот.

One next action: проверить изменения в Review на свежем `main`.

## LOG

### 2026-08-14 — Specification

Подтверждён недосчёт: короткий снимок `cycle()` является единственным источником
`attempts_so_far`, хотя это число включает диагностику, лимит стадии и жёсткую
остановку всей работы. Определён единый контракт: строгая пагинация с
дедупликацией, принадлежность по `work_id` и безопасный повтор без внешних
действий, если полную историю получить нельзя.

### 2026-08-14 — Implement

`route_question()` теперь получает авторитетный счётчик только из строгого
постраничного обхода задач; повтор cursor, предел страниц и ошибка API не
порождают внешних действий и возвращают терминальную задачу на следующий цикл.
Проверено: `python3 -m unittest -v pilot.test_pilot` — 296 passed, 13 skipped.

### 2026-08-14 — Implement

После перебазирования на свежий `main` конфликт разрешён в пользу полного
постраничного подсчёта, а не неполного снимка `cycle()`. Проверено: целевой
набор `RouteQuestionCompleteAttemptCountTests` — 5 passed.
