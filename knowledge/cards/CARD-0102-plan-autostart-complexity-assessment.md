# CARD-0102 — Карточки Плана получают оценку сложности при автозапуске

Implementation commit: faf476e453297c3f36e9a9e1c843542d1edc250d — автозапуск оценивает карточку, сохраняет основание и выбирает исполнителя по сложности.

## HEAD

- Status: Implement + Test complete — ожидает Review.
- Branch: `factory/6dd3aa2d-168-20411eeb-b70`.
- Implementation commit: `faf476e453297c3f36e9a9e1c843542d1edc250d`.
- Specification: `knowledge/specs/plan-autostart-complexity-assessment.md`.
- What changed: автозапуск строго получает и сохраняет `low|medium|high` с
  русским основанием, маршрутизирует первый этап по оценке и не запускает
  карточку при ошибке; План показывает оценку владельцу.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanAutostartTest
  pilot.test_pilot.PlanManualTaskTest` → 21 test, OK; `git diff --check` → OK.
- Next action: проверить diff и защитные сценарии на этапе Review.

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
