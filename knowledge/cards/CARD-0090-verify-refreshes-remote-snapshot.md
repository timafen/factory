# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

Implementation commit: 5d0d47dd98288d239239f4bfcfd94d48480d51d6 — Verify закрепляет свежий remote snapshot перед автоматическим слиянием.

## HEAD

Status: PASS.
Branch: `factory/258e646d-645-ec915b9c-8a7`.
Implementation commit: 5d0d47dd98288d239239f4bfcfd94d48480d51d6 — Verify закрепляет свежий remote snapshot перед автоматическим слиянием.
What changed: перед merge Verify заново получает изолированный снимок основной и delivery-ветки; сбой remote остаётся `BLOCKED: review infrastructure`.
What changed: сквозной fixture передаёт обязательный успешный snapshot и подтверждает его запрос для пересобранной delivery-ветки.
Evidence: `just test` — PASS; `python3 -m unittest pilot.test_pilot` — 225 tests OK (13 skipped).
Next action: Review сверить поставку с актуальной удалённой основной веткой.

## LOG

### 2026-08-12 — Implement

Verify больше не запускает автоматическое слияние по прежнему снимку Review:
перед merge он заново получает isolated remote snapshot с закреплёнными SHA.
При недоступности remote результат классифицируется как `BLOCKED: review infrastructure`;
целевой набор `FreshDefaultBranchSnapshotTests` прошёл (4 tests OK), полный `pilot.test_pilot` и проверка diff прошли.

### 2026-08-12 — Verify

| Критерий | Проверка | Наблюдаемый результат |
| --- | --- | --- |
| Verify получает свежую основную ветку и кандидата до merge | Изолированный fetch remote `main` и ветки кандидата; проверка `verify_gate` | Закреплены `base_sha=0ec9dd9e3f27a4ef0c5ce8a4503f1ba4d9ef0622` и `candidate_sha=ceaff8543210b022416a34dd7522a5c5abda0e4e`; gate вызывается до создания merge intent. |
| Ошибка обновления не разрешает merge | `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests` | 4 tests OK; при ошибке `fresh_branch_snapshot` возвращается `BLOCKED: review infrastructure`. |
| Нет регрессий проекта и артефактов | `just test`; `python3 -m unittest pilot.test_pilot`; `git diff --check` | Go-набор PASS и пробелы корректны, но Python-набор: 215 tests, 1 error, 13 skipped — `RebuiltDeliveryBranchPipelineTests.test_review_gate_rebuild_reaches_review_verify_and_merge` не создал `state["merge_intents"]["verify"]`. |

### 2026-08-12 — Implement

Сквозной fixture теперь передаёт обязательный успешный remote snapshot в настоящий `verify_gate`,
а не позволяет ему обращаться к сети; отдельно подтверждён запрос для пересобранной delivery-ветки.
`just test` прошёл; полный `python3 -m unittest pilot.test_pilot` завершился: 225 tests OK, 13 skipped.
