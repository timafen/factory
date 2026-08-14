Implementation commit: dab1bbbb27d2b82aa65d6a6c66e7e54fc138d25f — fixture доказывает fail-closed отказ при deleted inode без изменения артефактов или публикации версии.

# CARD-0127: Повтор предполётной проверки deleted-inode

## HEAD

Status: Implemented; ready for Review.
Branch: factory/037d4c9e-150-ad22f7ab-024.
Implementation commit: dab1bbbb27d2b82aa65d6a6c66e7e54fc138d25f — fixture доказывает fail-closed отказ при deleted inode без изменения артефактов или публикации версии.
What changed: `ops/test-fx-factory-release.sh` эмулирует активный `factory-server.service` с `MainPID` и `/proc/<pid>/exe` с суффиксом ` (deleted)`.
The fixture требует code 4, понятную строку с unit, неизменность install/live/database/release-info и отсутствие нового generation и service mutations.
Evidence: `bash -n ops/test-fx-factory-release.sh ops/fx-factory-release` → PASS; `bash ops/test-fx-factory-release.sh` → PASS.
One next action: Review проверить сценарий и передать его на системную root/systemd fixture.

## LOG

### 2026-08-14 — Specification

Определена отдельная диагностируемая операция: deleted inode останавливает выпуск до изменения Factory, а новая потеря supervisor output требует сохранить последний шаг и полный voyage-log, а не назвать попытку успешной.

Scope: `knowledge/specs/factory-release-preflight-deleted-inode-retry.md`, операционная проверка существующих `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`, `ops/test-factory-release-systemd.sh` и `docs/factory-handover-sol.md`.

### 2026-08-14 — Implement

Добавлен изолированный сценарий release fixture: активный `factory-server.service` возвращает MainPID, а его `/proc/<pid>/exe` помечен ` (deleted)`. Проверка подтверждает code 4, русскую диагностическую строку и отсутствие мутаций служб. `bash ops/test-fx-factory-release.sh` завершился успешно; systemd-проверка в текущем окружении явно SKIP, поскольку нет root/systemd fixture.

### 2026-08-14 — Implement

После замечания Review сценарий теперь снимает контрольный снимок install/live/database/release-info и каталога generations до запуска. После отказа он подтверждает полную неизменность снимка, отсутствие новой опубликованной версии и отсутствие service mutations. `bash -n ops/test-fx-factory-release.sh ops/fx-factory-release` и `bash ops/test-fx-factory-release.sh` завершились успешно.
