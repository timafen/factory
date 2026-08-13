# CARD-0103 — Разово закрыть старые зависшие карточки Плана

Implementation commit: 71dab9fafea4cc65e5b024a5a86a44a3f78a7702 — реализована безопасная разовая уборка старых карточек Плана.

## HEAD

- Status: Implemented and verified on current `main`.
- Branch: `factory/54202a7e-0a2-18a3d8fd-2c6`.
- Implementation commit: `71dab9fafea4cc65e5b024a5a86a44a3f78a7702`.
- What changed: операторская команда находит старые завершённые и потерявшие
  задачу карточки, делает dry-run по умолчанию и атомарно применяет изменения.
- Evidence: 14 target tests and 316 full Pilot tests passed; `just test`,
  `just build`, `py_compile` and `git diff --check` exited successfully.
- One next action: проверить dry-run с фактической датой внедрения перед применением.

## LOG

### 2026-08-12 — Implement

Реализована разовая консервативная уборка завершённых до границы и потерявших
задачу карточек. Защитные сценарии оставляют активные, отменённые, новые и
неоднозначные работы без изменений; повторное применение не переписывает файл.
Целевой и регрессионный классы: 11 tests, OK; `py_compile` и `git diff --check`
завершились с кодом 0.

### 2026-08-15 — Implement

Реализация перебазирована на `main` `9a8bdbd64ad29083877a3250aeea039e8a76f26e`
с сохранением новой повторной проверки брошенных запусков. Целевые 14 и полный
набор из 316 Pilot-тестов прошли; `just test`, `just build`, `py_compile` и
`git diff --check` завершились с кодом 0.
