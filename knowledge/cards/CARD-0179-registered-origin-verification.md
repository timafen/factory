Implementation commit: ba0c1ebfc8dc8f0586ec317d7c1fba2e722b0654 — проверка зарегистрированного origin до сети

## HEAD

Status: Implemented; ready for Review
Branch: factory/7d0667d3-722-782e5578-195
Implementation commit: ba0c1ebfc8dc8f0586ec317d7c1fba2e722b0654 — проверка зарегистрированного origin до сети
What changed: snapshot, refresh и rebuild сверяют URL локально зарегистрированного `origin` сразу после его создания.
What changed: при несовпадении адреса они завершаются до `_default_branch` и любой сетевой Git-операции.
Evidence: `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests` → 17 tests, OK.
Next action: повторить Review порядка сетевых Git-операций.

## LOG

### 2026-08-15 — Implement

Перенёс проверку `origin` перед определением default branch во все три изолированных Git-потока.
Добавил регрессионный тест: подменённый URL блокирует snapshot, refresh и rebuild без `_default_branch`, fetch, ls-remote или push.
