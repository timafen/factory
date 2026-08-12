# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

Implementation commit: 8b06957234a74357748edc44e81c290d4f053358 — Verify получает свежий изолированный снимок remote перед автоматическим слиянием.

## HEAD

Status: Implemented and tested; awaiting Review.
Branch: `factory/5cb1c940-460-2daa14cb-48d`.
Implementation commit: 8b06957234a74357748edc44e81c290d4f053358 — Verify получает свежий изолированный снимок remote перед автоматическим слиянием.
What changed: перед автоматическим merge Verify повторно получает pinned remote snapshot основной и кандидатной веток.
What changed: ошибка resolution/fetch останавливает merge с `BLOCKED: review infrastructure` и создаёт повтор Verify вместо ложного успеха.
Evidence: `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests` → 4 tests OK.
Evidence: `python3 -m unittest pilot.test_pilot` and `git diff --check` → PASS.
Next action: Review проверить безопасное продолжение Verify после восстановления remote.

## LOG

### 2026-08-12 — Implement

Verify больше не запускает автоматическое слияние по прежнему снимку Review:
перед merge он заново получает isolated remote snapshot с закреплёнными SHA.
При недоступности remote результат классифицируется как `BLOCKED: review infrastructure`;
целевой набор `FreshDefaultBranchSnapshotTests` прошёл (4 tests OK), полный `pilot.test_pilot` и проверка diff прошли.
