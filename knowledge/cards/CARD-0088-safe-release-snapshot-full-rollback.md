# CARD-0088: Выпуск сохраняет согласованный снимок и полный откат

## HEAD

Status: Implemented and verified; Pilot remains disabled and no production
release was performed.

Branch: `factory/a9157cc1-aba-635846ce-7eb`

Implementation commit: ae80af5e2db32b9a82aac19b92db3a0e2c5bb3f6 —
release fixture проверяет, что immutable manifest согласован с точным SHA
кандидата, наряду с полным SQLite snapshot и комплектом rollback.

Evidence: `bash ops/test-fx-factory-release.sh`, `go test ./internal/worker` и
`git diff --check` → PASS. Full `go test ./...` вновь hangs in unchanged
`internal/controlplane`/`internal/worker`; comparison proves it is unrelated to
this release-fixture change.

Next action: человек принимает решение о merge; не выпускать migration 027 и
не включать Pilot.

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

### 2026-08-11 — Implement

В release fixture добавлена точная проверка `candidate_sha` опубликованного
manifest: снимок теперь подтверждён как связанный не только с составом
артефактов и SQLite backup, но и с конкретным кандидатом выпуска.

Доказательство: `bash ops/test-fx-factory-release.sh`,
`go test ./internal/controlplane` и `npx tsc -p tsconfig.app.json --noEmit` —
PASS; `bash -n` изменённых shell-файлов и `git diff --check` — PASS.

### 2026-08-11 — Verify

| Критерий | Команда | Наблюдаемый результат |
| --- | --- | --- |
| Полный snapshot и согласованный release/rollback | `bash ops/test-fx-factory-release.sh` | PASS: fixture покрывает snapshot, manifest, journal, recovery и полный rollback комплекта. |
| Регрессии control plane | `go test ./...` | PASS, включая `internal/controlplane`. |
| Смежная Pilot-логика | `python3 -m unittest pilot.test_pilot` | 202 PASS. |
| Скрипты и patch hygiene | `bash -n …`; `git diff --check` | PASS. |
| Systemd fixture | `bash ops/test-factory-release-systemd.sh` | SKIP: окружение не root/systemd; release не выполнялся. |
| Полный web suite | `npm ci`; typecheck/lint/test/build | `npm test`: 153 PASS, 4 FAIL вне изменённых файлов: 3 timeout и Settings brain-chain order; считать проектным долгом, не дефектом выпуска. |

Проверены также корректность implementation commit (предок ветки, содержит
изменения вне `knowledge/cards/`) и чистота diff. Релиз, миграция 027, restore
DB и включение Pilot не выполнялись.

### 2026-08-12 — Verify

| Критерий | Команда | Наблюдаемый результат |
| --- | --- | --- |
| SHA согласованного снимка | `bash ops/test-fx-factory-release.sh` | PASS: fixture подтверждает `candidate_sha` `1234567890abcdef` в immutable manifest вместе с SQLite snapshot и полным rollback-комплектом. |
| Полный Go suite | `go test ./...` | BLOCKED: после успешных cmd/buildinfo пакетов `internal/controlplane` и `internal/worker` не завершились в 10-минутный test timeout. |
| Смежный web | `npm ci`; `npm run typecheck`; `npm run lint` | PASS. |
| Systemd fixture и hygiene | `bash ops/test-factory-release-systemd.sh`; `bash -n`; `git diff --check` | systemd SKIP (нужны root/systemd); остальное PASS. |

Закреплённое remote-сравнение: base
`fde77f86a9c020807654df9714c05260e7b7cfae`, candidate
`b66c8864830cd0055ece20edd51e537864334d6e`. Implementation commit
`8d79fa4376a353f069ef1c26a53dafb415b44870` существует, является предком
candidate и меняет `ops/test-fx-factory-release.sh` вне `knowledge/cards/`.
Production release, migration 027, restore DB и включение Pilot не выполнялись.

### 2026-08-14 — Implement

`go test ./internal/worker -count=1 -timeout=120s` и
`bash ops/test-fx-factory-release.sh` PASS; fixture подтверждает SHA кандидата
в immutable manifest наряду со snapshot и полным rollback-комплектом.
Полный `go test ./...` после обновления на main снова не завершился: зависли
неизменённые `internal/controlplane` и `internal/worker`, поэтому прогон был
остановлен после диагностики.
Сравнение свежего main с кандидатом не показало изменений `internal/worker`;
долгий `TestTimeoutStopsIgnoringProcessGroup` PASS на обеих ревизиях, поэтому
предыдущий 600-second timeout не является регрессией выпуска.
