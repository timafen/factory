Implementation commit: 0b385da2cc220ab6249a29e5c0ce91e6c764fc29 — fixture доказывает fail-closed отказ выпуска при deleted inode до мутаций.

# CARD-0127: Повтор предполётной проверки deleted-inode

## HEAD

Status: Implemented.
Branch: factory/af918838-ce0-d6326a25-705.
Implementation commit: 0b385da2cc220ab6249a29e5c0ce91e6c764fc29 — fixture доказывает fail-closed отказ выпуска при deleted inode до мутаций.
What changed: `ops/test-fx-factory-release.sh` эмулирует активный `factory-server.service` с `MainPID` и `/proc/<pid>/exe` с суффиксом ` (deleted)`.
The fixture требует code 4, понятную строку с unit и отсутствие service mutations.
Evidence: `bash -n ops/test-fx-factory-release.sh ops/fx-factory-release` → PASS; `bash ops/test-fx-factory-release.sh` → PASS.
One next action: выполнить `ops/test-factory-release-systemd.sh` в root/systemd CI fixture для проверки предпосылки на реальном MainPID.

## LOG

### 2026-08-14 — Specification

Определена отдельная диагностируемая операция: deleted inode останавливает выпуск до изменения Factory, а новая потеря supervisor output требует сохранить последний шаг и полный voyage-log, а не назвать попытку успешной.

Scope: `knowledge/specs/factory-release-preflight-deleted-inode-retry.md`, операционная проверка существующих `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`, `ops/test-factory-release-systemd.sh` и `docs/factory-handover-sol.md`.

### 2026-08-14 — Implement

Добавлен изолированный сценарий release fixture: активный `factory-server.service` возвращает MainPID, а его `/proc/<pid>/exe` помечен ` (deleted)`. Проверка подтверждает code 4, русскую диагностическую строку и отсутствие мутаций служб. `bash ops/test-fx-factory-release.sh` завершился успешно; systemd-проверка в текущем окружении явно SKIP, поскольку нет root/systemd fixture.
