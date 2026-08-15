Implementation commit: 93db3f1a2c3fb6e39203c2133c73c32582d6870b — `route_question()` считает попытки по полной строгой истории задач

# CARD-0162 — Стоп-кран считает всю историю попыток

## HEAD

Status: Implement + Test — готово к Review.

Branch: `factory/6831045e-ae2-6a1638ef-4b3`.

Implementation commit: `93db3f1a2c3fb6e39203c2133c73c32582d6870b`.

What changed: перед всеми нетехническими порогами `route_question()` получает
полную постраничную историю, дедуплицирует `task.id` и считает попытки той же
работы по `work_id` (с прежним legacy fallback). Неполная история снимает
терминальную задачу с `processed` без автоответа, паузы, вопроса или уведомления.

Evidence: `python3 -m unittest -v pilot.test_pilot.RouteQuestionCompleteAttemptCountTests pilot.test_pilot.DiagnosisRepairTests` — 22 tests, OK;
целевые проверки покрывают вторую страницу, разные `work_id`, дубль, повтор
cursor, ошибку API и нулевой режим ворот.

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
Проверено: `python3 -m unittest -v pilot.test_pilot.RouteQuestionCompleteAttemptCountTests pilot.test_pilot.DiagnosisRepairTests` — 22 tests, OK.
