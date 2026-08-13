# CARD-0097 — Неизменяемый снимок состава тупиков и причины архивирования

Implementation commit: a1c60a516ccbf4c3a8cdf581f0276f5d5e649de6 — Pilot snapshot pagination, immutable digest, archive reasons, and snapshot-aware efficiency.

## HEAD

- Status: Implemented — целевые проверки PASS; полный Go-набор остановлен на независимом integration timeout.
- Branch: `factory/0174c41c-7b0-9804ab1b-dcf`.
- Specification: `knowledge/specs/dead-end-work-snapshot-and-archive-reasons.md`.
- Owner decision: обязательный текущий контур — 73 работы; 74 — первоначальная
  скользящая метрика, пропавшая работа неидентифицируема.
- Scope: snapshot полного состава, digest, пагинация свыше 100, reason-коды
  архивирования и связь с efficiency; UI и продуктовые правила не меняются.
- What changed: Pilot получает все страницы, сохраняет идемпотентный snapshot с digest и reason-кодами; efficiency не считает недоказанные dead-end.
- Evidence: `python3 -m unittest pilot.test_pilot.DeadEndSnapshotTests pilot.test_pilot.WorkArchiveCleanupTests` → 10 OK; `go test ./internal/controlplane -run TestEfficiency -count=1` → PASS; `py_compile`/`git diff --check` → PASS.
- One next action: повторить полный `go test ./...` после устранения независимого integration timeout и влить ветку.

## LOG

### 2026-08-12 — Specification

Определены формат и границы будущего снимка: 73 уникальные записи с
`work_id`/`task_id`, временем и digest; историческое `reported_count=74` с
`missing_immutable_snapshot`; для каждой записи — включение, архивирование или
исключение с устойчивой причиной. Зафиксированы пагинация, идемпотентность,
atomic replace и регрессии для 101+ задач, повторного cleanup и настоящего
тупика.

Предыдущая ветка triage не разрешилась через origin; спецификация проверена
по свежему `origin/main` и фактическим файлам репозитория.

### 2026-08-12 — Implement

Внедрён полный постраничный сбор задач, неизменяемый digest-снимок с baseline
73 и историческим `reported_count=74`, стабильные причины архивирования и
связь `FinalDeadEnds` с доказанным snapshot. Целевые Python-тесты (10),
efficiency Go-тесты, синтаксис и `git diff --check` прошли; полный Go-набор
остановлен на независимом долгом integration-пакете.
