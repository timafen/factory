Implementation commit: 5fcb2acac2014f66d2ea93b495a2b042d3f22112 — безопасная проверка зарегистрированного origin до сети

## HEAD

Status: Implemented; ready for Review
Branch: factory/0170b460-82a-6ae335c8-a1c
Implementation commit: 5fcb2acac2014f66d2ea93b495a2b042d3f22112 — безопасная проверка зарегистрированного origin до сети
What changed: snapshot, refresh и rebuild сверяют локальный `origin` до `_default_branch` и любой сетевой Git-операции.
What changed: безопасный завершающий слеш допускается, а причины блокировки не раскрывают URL и секреты.
Evidence: `TemporaryRepositoryOriginTest` + `FreshDefaultBranchSnapshotTests` → 20 tests, OK.
Evidence: candidate `fee540601c6e64865851f5adb985a2ec6d28579b`, `just` 1.21.0 → build, format, vet, boundary, Go и 352 Pilot tests, OK.
Next action: Review подтверждает порядок проверки и безопасную диагностику.

## LOG

### 2026-08-15 — Implement

Перенёс проверку `origin` перед определением default branch во все три изолированных Git-потока.
Добавил регрессионный тест: подменённый URL блокирует snapshot, refresh и rebuild без `_default_branch`, fetch, ls-remote или push.

### 2026-08-15 — Implement

Уточнено безопасное сравнение URL: допускается только завершающий слеш, а ошибки
не включают зарегистрированный или канонический адрес. Четыре целевых сценария и
16 смежных проверок прошли; полный Verify закреплённого candidate также зелёный:
сборка, форматирование, vet, boundary, все Go-тесты и 352 Pilot-теста.
