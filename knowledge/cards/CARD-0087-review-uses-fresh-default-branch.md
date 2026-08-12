# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: Implemented — awaiting repeated Review.
Branch: `factory/fbfc83d6-91c-7d003cdd-58f`.
Implementation commit: 0ad547d2ad72476c1ea177e52cbb1a4f2826cbfe — Review/Verify сравнивают закреплённые SHA в изолированном bare-репозитории.
What changed: authoritative base/candidate refs fetch-ятся в отдельные refs bare-репозитория; delivery scope вычисляется точной командой `<base_sha>...<candidate_sha>`. Merge-base используется отдельно только для метрик.
Evidence: `python3 -m unittest pilot.test_pilot -q` — 226 tests OK (13 skipped); regression фиксирует `git init --bare` и точные аргументы pinned diff; `just build` — PASS.
Next action: повторить независимый Review относительно свежего remote default branch.

## LOG

### 2026-08-12 — Implement

Исправлены оба блокирующих замечания повторного Review: snapshot теперь создаётся
как bare-репозиторий, base/candidate fetch-ятся в его изолированные refs, а scope
вычисляется строго как `base_sha...candidate_sha`. Регрессия наблюдает точные
аргументы Git. `python3 -m unittest pilot.test_pilot -q` — 226 tests OK
(13 skipped); `just build` и `git diff --check` — PASS.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Сравнение закреплено на свежем remote default | `git ls-remote --symref origin HEAD`; isolated bare fetch; `git diff 0ec9dd9e3f27a4ef0c5ce8a4503f1ba4d9ef0622...7051218999e6dd67a3085c65adb51deb52b8c5a7` | PASS: default — `refs/heads/main`; оба полных SHA зафиксированы до сравнения; scope — только CARD-0087. |
| Реализационный коммит валиден | `git merge-base --is-ancestor ac3ef660715a20f7b50711a57f7d787f63883598 7051218999e6dd67a3085c65adb51deb52b8c5a7`; `git show --name-only` | PASS: коммит — предок кандидата, не tip карточки и меняет `pilot/config.example.json`, `pilot/pilot.py`, `pilot/test_pilot.py`. |
| Свежая база, SHA, BLOCKED и сохранение ветки | `python3 -m unittest pilot.test_pilot -q` | PASS: 214 тестов; fixture доказывает exact pinned scope, SHA reporting, infrastructure BLOCKED и отсутствие switch/reset worker branch. |
| Полная Go и статическая регрессия | `just test`; `just vet`; `just vuln`; `just staticcheck`; `just boundary`; `just format-check` | PASS: все Go-пакеты, анализ, vulnerability scan и архитектурная граница чисты. |
| UI и живой сервер | `just ui-check`; `just ui-build 0`; `just test-browser` | PASS: lint/typecheck/158 component tests; embedded assets актуальны; 21 Playwright-сценарий прошёл против реального Go-сервера. |
| Сборка и эксплуатационные сценарии | `just build`; `just test-tooling`; `just test-release`; `just test-launcher` | PASS: бинарники собраны, release воспроизводим, tooling и launcher прошли. |
| Live rollout и rollback | зафиксированный smoke revisions 7→8→9; `sudo -n /usr/local/bin/fx factory status`; `sudo -n /usr/local/bin/fx factory health` | PASS: новая политика применена, штатно откатана и повторно применена; Factory сейчас active, интерфейс и данные — HTTP 200. |

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

### 2026-08-11 — Implement

Свежий `main` выпущен штатной командой `fx factory release main`; Factory health
подтвердил HTTP 200. Для Review и Verify созданы immutable revisions: новая
политика (7), штатный возврат к прежней (8) и повторное применение новой (9).
Smoke чтением live Workflow API и revision history подтвердил, что обе текущие
ревизии — 9 и содержат правило CARD-0087; существующие snapshots не менялись.

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
