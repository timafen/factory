# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

Implementation commit: 8b06957234a74357748edc44e81c290d4f053358 — Verify получает свежий изолированный снимок remote перед автоматическим слиянием.

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/5cb1c940-460-2daa14cb-48d`.
Implementation commit: 8b06957234a74357748edc44e81c290d4f053358 — Verify получает свежий изолированный снимок remote перед автоматическим слиянием.
What changed: перед автоматическим merge Verify повторно получает pinned remote snapshot основной и кандидатной веток.
What changed: ошибка resolution/fetch останавливает merge с `BLOCKED: review infrastructure` и создаёт повтор Verify вместо ложного успеха.
Evidence summary: `just test` passed; `FreshDefaultBranchSnapshotTests` passed (4 tests); pinned comparison, `git diff --check`, and clean candidate tree passed.
Next action: Human merge the verified delivery into `main`.

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
| Нет регрессий проекта и артефактов | `just test`; `git diff --check`; `git status --short` | Go-набор PASS; пробелы корректны; дерево кандидата чистое. |
