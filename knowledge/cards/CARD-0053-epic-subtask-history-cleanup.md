# CARD-0053 — Завершение подзадач эпика переживает очистку истории

## HEAD

- Status: Verified PASS — готово к слиянию.
- Branch: `factory/e7e402a3-f91-babd2028-96a`.
- Head commit: `c98365d` (реализация CARD-0053).
- What changed: Пилот сохраняет квитанцию завершения подзадачи в эпике и после очистки истории восстанавливает running-подзадачу только по точному свежему merge.
  `hold_reason` удерживает запуск; новое поколение отсекает старую квитанцию, а `parallel_ok` остаётся независимым.
- Evidence: `python3 -m unittest pilot.test_pilot` → 114 tests OK; `just build` → OK.
- One next action: влить проверенную ветку в `main`.

## LOG

### 2026-08-10 — Implement

Перенесена целевая реализация из полной ветки `factory/be2db5ef-76a-dcdec47d-671`
на свежий `origin/main`; общий backlog CARD-0030 не изменялся. Регрессионные тесты
покрывают сохранение квитанции после очистки, точное и свежее совпадение merge,
запрет старого merge, `hold_reason`, новое поколение и сохранение `parallel_ok`.
`python3 -m unittest pilot.test_pilot` завершился 114 проверками OK; `just build` прошёл.
