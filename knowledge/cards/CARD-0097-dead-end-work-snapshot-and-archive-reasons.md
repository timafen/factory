# CARD-0097 — Неизменяемый снимок состава тупиков и причины архивирования

Implementation commit: c991e232cc627be8844ef3760d81494b47189f2d — снимок фиксирует ровно 73 аварийные работы до cleanup, а digest не зависит от времени.

## HEAD

- Status: Implemented — целевые проверки PASS.
- Branch: `factory/dfe0c8b5-52a-2645e5ec-f6b`.
- Specification: `knowledge/specs/dead-end-work-snapshot-and-archive-reasons.md`.
- Owner decision: обязательный текущий контур — 73 работы; 74 — первоначальная
  скользящая метрика, пропавшая работа неидентифицируема.
- Scope: snapshot полного состава, digest, пагинация свыше 100, reason-коды
  архивирования и связь с efficiency; UI и продуктовые правила не меняются.
- What changed: Pilot отбирает и проверяет ровно 73 failed-работы до cleanup; время захвата исключено из канонического digest.
- Evidence: `python3 -m unittest pilot.test_pilot.DeadEndSnapshotTests pilot.test_pilot.WorkArchiveCleanupTests` → 11 OK; `go test ./internal/controlplane -run TestEfficiency -count=1` → PASS; `py_compile`/`git diff --check` → PASS.
- One next action: выполнить Verify и влить ветку.

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

### 2026-08-12 — Implement

По решению владельца снимок теперь получает до cleanup только failed-работы
аварийного контура и публикуется лишь при точно проверенном составе из 73
уникальных `work_id`; неизвестный состав не обрезается молча. Канонический
digest больше не включает `captured_at`: отдельный тест создаёт одинаковый
состав в разное время и подтверждает один digest. Целевые Python-тесты (11),
Go efficiency-проверка, синтаксис и `git diff --check` прошли.
