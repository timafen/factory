# CARD-0088: Выпуск сохраняет согласованный снимок и полный откат

## HEAD

Status: Implemented and verified; Pilot remains disabled and no production
release was performed.

Branch: `factory/00a0a965-4e1-ac3fb722-fe9`

Implementation commit: 044c941ee845c917967f3f2a25ed64d3367502a6 —
выпуск сохраняет проверенный SQLite snapshot и immutable полный комплект,
устанавливает пару через journal и полностью откатывает код/службы/metadata;
DB restore остаётся отдельной подтверждаемой операцией.

Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `go test ./...` → PASS;
`python3 -m unittest pilot.test_pilot` → 202 PASS; UI type/test/build → 157 PASS
и build PASS; `bash ops/test-factory-release-systemd.sh` → явный SKIP вне root
systemd fixture; shell syntax и `git diff --check` → PASS.

Next action: провести независимый Review реализации CARD-0088 до любого выпуска
migration 027 или включения Pilot.

## LOG

### 2026-08-11 — Specification

Finding: worker-discovered high-risk release finding, не ручное предложение
владельца. Production не считать rollback-ready и не изменять в рамках этой
карточки.

Specification:
`knowledge/specs/factory-release-consistent-snapshot-full-rollback.md`.

## Результат для владельца

Выпуск до любой мутации создаёт проверенный SQLite online snapshot, связанный с
точным ledger/schema и candidate SHA, и публикует immutable manifest полного
server/worker/broker/control/brain/metadata комплекта с идентичностями процессов.
Unknown/mixed/deleted процессы, отсутствующий rollback artifact, неверные права
или нехватка места блокируют выпуск.

Установка, health и metadata образуют crash-safe транзакцию. Обычный rollback
возвращает весь комплект и состояния служб, но никогда автоматически не меняет
БД. DB restore — отдельная подтверждаемая high-risk операция в новый файл с
проверкой integrity/ledger/schema и сохранением failed DB.

## Scope реализации

- `ops/fx-factory-release`
- `ops/fx`
- `ops/test-fx-factory-release.sh`
- `ops/test-factory-release-systemd.sh`
- `internal/controlplane/recovery_test.go`

## Приёмка и доказательство

Обязательное доказательство: `bash ops/test-fx-factory-release.sh` завершено с
кодом 0. Дополнительно нужны реальные systemd/process fixtures, SQLite
backup/restore 026→027, crash boundaries, retention/permissions/disk проверки
и `git diff --check`, как определено спецификацией.

## Ограничения и следующее действие

Эта карточка не разрешает release, изменение production, служб, БД, скриптов
или live config. Не включать Pilot и не выпускать migration 027 до принятой
реализации.

Next action: передать CARD-0088 в Implement по точному scope спецификации.

### 2026-08-11 — Implement

Реализованы fail-closed preflight, online SQLite snapshot, канонический manifest
полного поколения, fsync journal и восстановление после фазовых прерываний.
Обычный rollback возвращает парные binaries, broker/control/brain, metadata и
service states без изменения БД; несовместимый ledger требует отдельный
проверенный `restore-db`, сохраняющий failed DB.

Доказательство: обязательный release fixture PASS, Go `./...` PASS, Pilot 202
PASS, UI 157 PASS и production build PASS, syntax/diff PASS. Реальная systemd
фикстура добавлена и вне root/systemd окружения честно завершилась SKIP.
