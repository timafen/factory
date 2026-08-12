# CARD-0088: Выпуск сохраняет согласованный снимок и полный откат

## HEAD

Status: Specification — implementation required before migration 027; Pilot
remains disabled.

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
кодом 0 после добавления целевого сценария: online snapshot при записи связан с
manifest, сбой после установки возвращает полный прежний комплект, состояния и
metadata, а live DB остаётся byte-for-byte прежней. Дополнительно нужны реальные
systemd/process fixtures, SQLite backup/restore 026→027, crash boundaries,
retention/permissions/disk проверки и `git diff --check`, как определено
спецификацией.

## Ограничения и следующее действие

Эта карточка не разрешает release, изменение production, служб, БД, скриптов
или live config. Не включать Pilot и не выпускать migration 027 до принятой
реализации.

Next action: передать CARD-0088 в Implement по точному scope спецификации.
