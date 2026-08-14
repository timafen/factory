# CARD-0127: Повтор предполётной проверки deleted-inode

## HEAD

Status: Implemented.
Branch: factory/cf5becf8-54e-6460fa79-959.
Implementation commit: 60dad1f67ba638f2ff03e6eccf6c9677a77d5799 — fixture выпуска проверяет отказ при deleted-inode до мутаций.
What changed: добавлен изолированный сценарий активного unit с `/proc/<pid>/exe` на deleted inode; gate обязан назвать unit и завершиться до journal/current generation.
Evidence: `FACTORY_TEST_ONLY=deleted-inode bash ops/test-fx-factory-release.sh` → PASS; `bash -n ops/test-fx-factory-release.sh` → PASS.
One next action: выполнить полный `bash ops/test-fx-factory-release.sh` и systemd fixture перед публикацией.

## LOG

### 2026-08-14 — Implement

Добавлено покрытие fail-closed preflight для deleted-inode: имитируется активный
`factory-worker.service`, проверяются код 4, диагностическое имя unit и отсутствие
событий остановки, transaction journal и current generation. Целевой сценарий и
синтаксическая проверка прошли; production gate и проверка `/proc/<pid>/exe` не менялись.
