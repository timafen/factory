# CARD-0102 — Карточки Плана получают оценку сложности при автозапуске

Implementation commit: c9f5b18feed78a415e0380d94012ce8623069b29 — автозапуск оценивает карточку, сохраняет основание и выбирает исполнителя по сложности.

## HEAD

- Status: Verified PASS — ожидает человеческого слияния.
- Branch: `factory/6dd3aa2d-168-20411eeb-b70`.
- Implementation commit: `c9f5b18feed78a415e0380d94012ce8623069b29`.
- Specification: `knowledge/specs/plan-autostart-complexity-assessment.md`.
- What changed: автозапуск строго получает и сохраняет `low|medium|high` с
  русским основанием, маршрутизирует первый этап по оценке и не запускает
  карточку при ошибке; План показывает оценку владельцу.
- Evidence: сборка трёх бинарников прошла; 21 целевой тест и 165 UI-тестов
  прошли; Go, tooling и launcher зелёные; pinned `git diff --check` — OK.
- Next action: человеку слить ветку в `main`.

## LOG

### 2026-08-12 — Implement

Добавлена строгая оценка сложности до создания задачи, её сохранение и повторное
использование, маршрутизация Triage по оценке и отказ от запуска при невалидном
ответе модели. Экран Плана показывает русскую сложность и экранированное
основание, а старые карточки помечает как ещё не оценённые. Целевые 21 тест
автозапуска и экрана Плана прошли успешно; `git diff --check` не нашёл ошибок.

### 2026-08-12 — Specification

Фактический код подтвердил, что автозапуск всегда передаёт в `stage_worker`
константу `medium`, а карточка не хранит сложность. Определена единая граница:
до создания задачи получить строгую оценку `low|medium|high`, сохранить её с
русским основанием, использовать для первого worker и повторно не оценивать.
Невалидная оценка не маскируется как `medium` и не переводит карточку в работу.

Предыдущая Triage-ветка `factory/b6ffc762-239-c969ae3d-2ea` отсутствовала в
origin на момент Specification; документ опирается на свежий `origin/main` и
фактические тестовые границы `PlanAutostartTest`.

### 2026-08-12 — Implement

Реализация перенесена на `507abf5bacde7075cd09b137a0623d78086e9aa4`
(`origin/main`) без изменения области. После rebase прошли 21 целевой
тест `PlanAutostartTest` и `PlanManualTaskTest`; `py_compile` и
`git diff --check origin/main...HEAD` завершились успешно.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Оценка сохраняется до создания задачи | `PlanAutostartTest.test_unrated_card_is_assessed_saved_and_routed_before_creation` | PASS: сохранены `high` и русское основание до POST |
| Worker и Triage получают одну оценку | тот же тест и `test_starts_top_planned_card_with_triage_context` | PASS: выбран high-worker, контекст содержит оценку и основание |
| Повтор не вызывает модель | `test_saved_assessment_is_reused_without_brain`, `test_retry_after_uncertain_post_uses_same_card_request_key` | PASS: brain не вызван, request-key стабилен |
| Невалидный ответ не запускает карточку | `test_invalid_assessments_fail_closed_and_notify_owner` | PASS: worker/POST/state не меняются, владелец уведомлён |
| Данные карточки не расширяют словарь | `test_assessment_accepts_only_the_three_supported_tiers` | PASS: приняты только low/medium/high, ввод помечен недоверенным |
| План показывает оценку и legacy-состояние | `PlanManualTaskTest.test_task_action_promotes_card_and_creates_task` | PASS: русская подпись, экранированное основание, «ещё не оценена» |
| Соседнее поведение не регрессировало | весь `PlanAutostartTest` и `PlanManualTaskTest` | PASS: 21 тест очереди, alias, лимитов, retry и маршрутизации |

Финальная сборка создала `factory-server`, `factory-worker` и
`factory-release-broker`; `just test`, UI 165/165, tooling и launcher прошли.
Полный Python-набор: 251 тест, 2 известных падения
`CorrectionProvenanceStormTests`, которые воспроизводятся на закреплённом
`main`; `just check` также останавливается на существующем `SA4000` в
`internal/worker/attempt_lifecycle_test.go:31`, не входящем в поставку.
