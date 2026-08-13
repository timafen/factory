# CARD-0069 — Спецификация сохраняется в ветке до разработки

## HEAD

Implementation commit: 9bda146003105ee1bdbce2a1c290bc8e2cbf2b2b — Пилот проверяет сохранность спецификации перед разработкой.

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/421ef5eb-ef6-3168645c-592`.
- Specification: `knowledge/specs/specification-branch-handoff.md`.
- What changed: переход запускает разработку только после подтверждения
  опубликованной ветки с непустым diff; временный сбой GitHub ждёт новый цикл.
- Evidence: `just test` → all Go packages OK; `python3 -m unittest -v
  pilot.test_pilot` → 176 tests, OK, including
  `SpecificationBranchHandoffTests`.
- Next action: выполнить human merge в main.

## LOG

### 2026-08-11 — Specification

Подтверждён разрыв в текущем переходе: опубликованная ветка выбирается и
проверяется только перед Review/Verify, тогда как Specification сразу создаёт
Implement + Test по имени ветки из текста. Выбран минимальный контракт: до
разработки ветка обязана существовать в origin и иметь непустой diff относительно
main; временная ошибка GitHub откладывает переход без ложного возврата.

### 2026-08-11 — Implement

Добавлены ворота сохранности перед `Implement + Test`: выбранная опубликованная
ветка обязана существовать и иметь непустой diff относительно `main`. Отсутствие
артефакта возвращает `Specification` с инструкцией commit/push, а временная ошибка
GitHub снимает задачу из `processed` для следующего цикла. Целевой набор: 8 tests,
OK; смежные ворота поставки: 9 tests, OK; `py_compile` и `git diff --check`: OK.

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдаемый результат |
| --- | --- | --- |
| Опубликованная непустая ветка запускает одну разработку с подтверждённой веткой | `SpecificationBranchHandoffTests.test_published_nonempty_branch_starts_implementation` и `test_handoff_uses_published_branch_instead_of_stale_first_mention` | Создаётся одна `Implement + Test`, context содержит опубликованную ветку. |
| Отсутствующая или пустая ветка возвращает Specification | `test_missing_branch_returns_same_specification`, `test_empty_branch_diff_returns_same_specification` | Разработка не создаётся; повторная задача требует commit/push. |
| Нет имени ветки — безопасный возврат | `test_absent_branch_name_returns_same_specification` | Создаётся Specification с объяснением отсутствующего имени. |
| Сбой GitHub ждёт повторной проверки | `test_github_error_retries_without_creating_any_stage`, `test_branch_report_raises_on_service_failure` | Не создаётся ни стадия разработки, ни новая спецификация; задача доступна следующему циклу. |
| Другие переходы и обещания не ослаблены | `python3 -m unittest -v pilot.test_pilot`; `just test` | 176 Python-тестов и все Go-пакеты завершились OK. |

Дополнительно: `git diff --check origin/main...HEAD` без ошибок; рабочее дерево
чисто. Реализационный commit существует, является предком ветки и меняет
`pilot/pilot.py`, `pilot/test_pilot.py` и спецификацию, а не только карточку.
