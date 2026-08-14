# CARD-0127: Повтор предполётной проверки deleted-inode

## HEAD

Status: Implemented.
Branch: factory/fc12a18a-f22-e5d57bb6-523.
Implementation commit: 263deff0fcad3e6444cb10bebadda0059df5b3cf — fixture доказывает fail-closed отказ выпуска при deleted inode до мутаций.
What changed: `ops/test-fx-factory-release.sh` проверяет активные `factory-worker.service` и `factory-server.service` с `/proc/<pid>/exe` на deleted inode.
The fixture требует code 4, понятную строку с unit и отсутствие service mutations.
Evidence: целевой и полный `bash ops/test-fx-factory-release.sh` → PASS; `bash -n ops/test-fx-factory-release.sh` → PASS; systemd fixture → SKIP без root.
One next action: выполнить `ops/test-factory-release-systemd.sh` в root/systemd CI fixture.

## LOG

### 2026-08-14 — Specification

Определена отдельная диагностируемая операция: deleted inode останавливает выпуск до изменения Factory, а новая потеря supervisor output требует сохранить последний шаг и полный voyage-log, а не назвать попытку успешной.

Scope: `knowledge/specs/factory-release-preflight-deleted-inode-retry.md`, операционная проверка существующих `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`, `ops/test-factory-release-systemd.sh` и `docs/factory-handover-sol.md`.

### 2026-08-14 — Implement

Добавлен изолированный сценарий release fixture: активный `factory-server.service` возвращает MainPID, а его `/proc/<pid>/exe` помечен ` (deleted)`. Проверка подтверждает code 4, русскую диагностическую строку и отсутствие мутаций служб. `bash ops/test-fx-factory-release.sh` завершился успешно; systemd-проверка в текущем окружении явно SKIP, поскольку нет root/systemd fixture.

### 2026-08-14 — Implement

После перебазирования на свежий `main` сохранён сценарий worker deleted-inode и
совместимость полного server fixture. Целевой и полный тесты прошли; systemd fixture
явно пропущен без root.
