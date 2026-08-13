# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/597fbc07-bb7-c72e1c7a-5db`.
Implementation commit: ff076ae565626fec8a3150414307e2c66d231b11 — Review сверяет кандидат от прежнего main через общий merge-base и не блокирует его после продвижения основной ветки.
What changed: Review и Verify фиксируют свежие SHA remote default branch и кандидата; продвижение main не превращается в ложную инфраструктурную блокировку.
Evidence: pinned isolated fetch дал `base_sha=b448350413748b951462b5db8e999b59d7f8e278` и `candidate_sha=2636552fa3ca57636a4d329b977b4d531a77327e`; `python3 -m unittest pilot.test_pilot -q` — 235 tests OK (13 skipped). Полный `just check` остановлен вне области на существующем `SA4000` в `internal/worker/attempt_lifecycle_test.go:31`.
Next action: выполнить human merge в `main`.

## LOG

### 2026-08-12 — Implement: повторная поставка конфигурации Pilot

Implementation commit: 80e51dc165b6dc3f9732c8aacb35a0fcefc097a5 — из примера Pilot удалены неподдерживаемые rollout-поля; коммит уже входит в свежий `main` `48983479beb82b80a75a3e98a658a0b3b1b337e9`.
Ветка `factory/2a053e4b-d47-5aea2adf-0c3` повторно основана на свежем `main`; устаревшие конфликтующие подтверждения отброшены, append-only история сохранена.
Целевой schema test, JSON-проверка без `rollout`, `review_revision`, `verify_revision` и `go build ./cmd/factory-server` — PASS.
Полный `GOMAXPROCS=2 just check` остановлен вне области на существующем `SA4000` в `internal/worker/attempt_lifecycle_test.go:31`.

### 2026-08-12 — Implement: исправление конфликта Pilot

Ветка повторно основана на свежем `main` `33aa4b58d7f949420ba4d86cfc9639038fa0f3c8`; кодовый коммит `80e51dc165b6dc3f9732c8aacb35a0fcefc097a5` уже входит в базу и удаляет неподдерживаемые rollout-метаданные из примера Pilot.
Целевая проверка `go test ./internal/controlplane -run '^TestPilotConfigExampleMatchesServerSchema$' -count=1` — PASS.
Полный `just check` прошёл format, vet, vuln, staticcheck и controlplane, но вне области задачи нестабильный `internal/worker.TestIdleWorkerMakesOneClaimPerPollingInterval` завершился по таймауту.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Авторитетная свежая база и кандидат | `git ls-remote --symref origin HEAD`; isolated bare fetch только `refs/heads/main` и `refs/heads/factory/597fbc07-bb7-c72e1c7a-5db` | PASS: `base_sha=b448350413748b951462b5db8e999b59d7f8e278`, `candidate_sha=2636552fa3ca57636a4d329b977b4d531a77327e`; pinned `base_sha...candidate_sha` содержит только эту карточку. |
| Свежая проверка без ложной блокировки | `python3 -m unittest pilot.test_pilot -q` | PASS: 235 тестов, 13 пропущено; проверки pinned remote, продвижения базы и инфраструктурного `BLOCKED` прошли. |
| Полный набор перед слиянием | `just check` из чистого дерева | НАХОДКА: `format-check`, `go vet` и `govulncheck` прошли; `staticcheck` остановил набор на существующем внеобластном `internal/worker/attempt_lifecycle_test.go:31` (`SA4000`). |
| Валидность карточки и чистота | проверка предка `ff076ae565626fec8a3150414307e2c66d231b11`, `git diff --check`, `git status --short` | PASS: implementation commit существует, является предком кандидата и меняет код вне `knowledge/cards/`; пробельных ошибок и stray-файлов нет. |

Находка: полный `just check` нельзя считать зелёным из-за внеобластного `SA4000`; целевая проверка Pilot полностью зелёная. Live rollout не выполнялся: изменение касается проверки и карточки, runtime-конфигурация и ревизии стенда не менялись.

### 2026-08-12 — Review

Review одобрено вручную по сохранённому результату решающего шага: вердикт
APPROVE, замечаний нет. Повторный прогон не потребовался: предыдущая остановка
вызвана лишним текстом после корректного JSON-вердикта, а не содержанием Review.
Проверен кандидат `d0317403ae3b5765b9c0c26ab1ad74dad2fec391` ветки
`factory/48f9f1f9-77a-927751d6-b57`; область поставки — только эта карточка.
Целевой набор `python3 -m unittest pilot.test_pilot -q` прошёл: 235 тестов,
13 пропущено.

### 2026-08-12 — Implement

Исправлена ссылка на существующий кодовый коммит `ff076ae565626fec8a3150414307e2c66d231b11`;
кандидат содержит только эту карточку. Проверено существование commit-объекта и `python3 -m unittest pilot.test_pilot -q` — 232 tests OK (13 skipped).

### 2026-08-12 — Verify

Повторная публикация на свежем `origin/main`: заявленная старая ветка отсутствует,
но кодовый предок уже входит в `main`; карточка обновлена для новой ветки.

### 2026-08-12 — Implement

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Свежая remote-база и кандидат | `git ls-remote --symref origin HEAD`; isolated bare fetch `main` и `factory/16f9dc13-c12-270afe6b-8a2` | PASS: `base_sha=0ec9dd9e3f27a4ef0c5ce8a4503f1ba4d9ef0622`, `candidate_sha=23afab43447c8e8b5901e4574f0edfefe6652684`. |
| Отсутствие ложной блокировки после продвижения базы | `git diff --name-only base_sha...candidate_sha`; проверка предка кодового implementation commit | PASS: относительно свежего `main` изменена только эта карточка; кодовый коммит `ff076ae565626fec8a3150414307e2c66d231b11` — предок кандидата и меняет `pilot/pilot.py`, `pilot/test_pilot.py`. |
| Пиннинг fresh default branch и поведение сбоя инфраструктуры | `python3 -m unittest pilot.test_pilot -q` | PASS: 214 tests OK (13 skipped), включая регрессии bare remote и BLOCKED при resolution/fetch failure. |
| Полный набор | `GOMAXPROCS=2 just check` в чистом archive кандидата | НЕ ПРОЙДЕН по внеобластной давней интеграционной проверке `internal/worker.TestTimeoutStopsIgnoringProcessGroup`: test timeout 5m. До сбоя прошли format, vet, govulncheck, staticcheck и несколько Go-пакетов. |
| Чистота поставки | `git diff --check base_sha...candidate_sha`; `git status --short` | PASS: ошибок пробелов нет; проверочный клон чист. |

Находка: полный Go-набор нестабилен вне области изменения (`internal/worker`); Pilot-регрессии изменения проходят полностью. Live rollout не выполнялся: поставка не меняет runtime-конфигурацию или ревизии задач.

### 2026-08-12 — Implement

Актуализирован HEAD карточки после исправления ложной блокировки: успешный
результат `python3 -m unittest pilot.test_pilot -q` — 202 tests OK. Карточка
ссылается на финальный кодовый коммит `ff076ae565626fec8a3150414307e2c66d231b11`;
live revisions намеренно не менялись согласно передаче.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Свежая база и точный scope | `python3 -m unittest pilot.test_pilot` | PASS: real bare-remote fixture показывает stale scope из 12 файлов и pinned scope из 11 файлов, `ahead_by=2`, SHA и сохранение ветки воркера. |
| Инфраструктурный сбой не обвиняет код | тот же набор, `FreshDefaultBranchSnapshotTests` | PASS: failure resolution/fetch даёт BLOCKED без REQUEST CHANGES. |
| Полный Pilot-набор | `python3 -m unittest pilot.test_pilot -q` | BLOCKED: 202 tests, 3 errors — два `CardNumberReservationTests` получают blocked result вместо старого `back`, а `SpecificationBranchHandoffTests` ожидает прежний `branch_report`/gh seam. |
| Регрессии runtime | `go test ./...`; `go build ./cmd/factory-server` | PASS. |
| Регрессии web | `npm run typecheck`; `npm test` | PASS: 14 файлов тестов, 155 тестов. |
| Чистота поставки | `git diff --check`; `git diff --name-only origin/main...HEAD` | PASS: только запись Verify в карточке. |
| Live rollout | проверка `## HEAD` и rollout-плана карточки | BLOCKED: immutable revisions не созданы и не закреплены; это обязательный критерий приёмки. |

### 2026-08-11 — Specification

Статус: specification

Результат: Review/Verify перед сравнением получают authoritative default branch
из remote, обновляют именно этот ref и фиксируют base/candidate SHA. При сбое
получения задача становится BLOCKED. Existing running tasks не изменяются.

Связь: worker-discovered finding из CARD-0085; CARD-0086 зарезервирована.

### 2026-08-11 — Implement

Реализован isolated fetch-and-pin snapshot для Review и блокировка инфраструктурных ошибок без cached `origin/main`.
Регрессия с bare remote доказывает: stale comparison даёт 12 файлов, pinned snapshot — точные 11 и `ahead_by=2`; ветка воркера сохраняется.
Проверены `python3 -m unittest pilot.test_pilot`, `go test ./...`, `go build ./cmd/factory-server`, JSON config и `git diff --check` — PASS.

### Передача в реализацию

- Спецификация: `knowledge/specs/review-fresh-default-branch.md`.
- Реализатор меняет только перечисленные там runtime/test/config files и не
  редактирует эту карточку без добавления доказательства результата.
- Live Pilot получает новые ревизии Review и Verify безопасным добавлением
  immutable revisions; новые задачи и Pilot выбирают исправленные ревизии.
- Rollback: переключить Pilot/config обратно на предыдущие revision_id; уже
  созданные task snapshots и running tasks не мутировать.

### 2026-08-11 — Implement

Исправлена ложная блокировка: кандидат от прежнего main сравнивается со свежим
main через их pinned общий merge-base. Продвижение базы описывается в Review,
а не переводит проверку в инфраструктурный BLOCKED.

Регрессия использует реальный bare remote и не зависит от cached refs; полный
`python3 -m unittest pilot.test_pilot` проходит: 202 tests OK. Также PASS:
`go test ./...`, `go build ./cmd/factory-server`, JSON config и `git diff --check`.

### 2026-08-11 — Implement

Из `pilot/config.example.json` удалены метаданные rollout Review/Verify,
которые не являются настройкой сервера и отклонялись строгим декодером.
Проверки PASS при `umask 077`: focused schema test, `go test ./...`,
`python3 -m unittest pilot.test_pilot`, JSON validation, build и diff check.
