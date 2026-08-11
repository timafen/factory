# CARD-0059 — «Сделано недавно» показывает только завершённую работу

Implementation commit: 1344c86f79e082404401d3f2767498e5312a00ca — успешные промежуточные этапы исключены из «Сделано недавно».

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/713cf42c-248-9ea02867-e59`.
- Implementation commit: 1344c86f79e082404401d3f2767498e5312a00ca — успешный этап отображается только после подтверждённого слияния.
- What changed: успешный Triage и неподтверждённый Verify больше не считаются завершённой работой.
- What changed: подтверждённые слияния, конечные ошибки и отмены сохраняют прежнее поведение.
- Evidence: полный набор `just check && just test-browser && just test-release && just test-worker-race` завершён успешно; `just build` собрал бинарники.
- One next action: проверить изменения и влить ветку в main.

## LOG

### 2026-08-10 — Implement

Блок «Сделано недавно» теперь опирается на журнал слияний для успешных результатов и не выдаёт промежуточный Triage за законченную работу. Целевые пять сценариев прошли; проект собран без ошибок.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Успешный Triage не попадает в «Сделано недавно» | `RecentDoneTest.test_ignores_succeeded_intermediate_triage` в `just check` | Пустой список, API не вызывается. |
| Успешный Verify без слияния исключён, а подтверждённое слияние остаётся | `RecentDoneTest.test_excludes_successful_progress_and_unmerged_verify` в `just check` | Отображены только слитая работа и терминальная ошибка. |
| Терминальные результаты и фильтр служебных финалов не регрессировали | `RecentDoneTest.test_keeps_real_pipeline_results_and_excludes_five_service_finals` в `just check` | Реальная ошибка и слияние сохранены, служебные финалы исключены. |
| Проект собирается и проходит полный набор проверок | `just check && just test-browser && just test-release && just test-worker-race`; `just build` | Успешно. |
