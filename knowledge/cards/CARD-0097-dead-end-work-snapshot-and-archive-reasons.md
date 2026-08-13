# CARD-0097 — Неизменяемый снимок состава тупиков и причины архивирования

Implementation commit: a64bb4fae6d63334f154531de0a48c08ac275aec — решения снимка фиксируются до cleanup, публикация атомарна.

## HEAD

- Status: Implemented — замечания Review исправлены, целевые проверки PASS.
- Branch: `factory/b2406582-9b2-6474aafb-b35`.
- Specification: `knowledge/specs/dead-end-work-snapshot-and-archive-reasons.md`.
- Owner decision: обязательный текущий контур — 73 работы; 74 — первоначальная
  скользящая метрика, пропавшая работа неидентифицируема.
- Scope: snapshot полного состава, digest, пагинация свыше 100, reason-коды
  архивирования и связь с efficiency; UI и продуктовые правила не меняются.
- What changed: Pilot сохраняет pre-cleanup решения отдельно от изменяемых архивов; снимок публикуется через временный файл, flush/fsync и os.replace.
- Evidence: `python3 -m unittest pilot.test_pilot.DeadEndSnapshotTests pilot.test_pilot.WorkArchiveCleanupTests` → 12 OK; `py_compile`/`git diff --check` → PASS.
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

### 2026-08-12 — Implement

По замечаниям Review решения снимка вычисляются до изменения `works.json` и
`work_status.json`, а writer получает этот неизменяемый контекст. Публикация
выполняется через временный файл в том же каталоге с `flush`/`fsync` и `os.replace`;
регрессия проверяет сохранение `included` после cleanup и отсутствие временного файла.
Целевые Python-тесты (12), `py_compile` и `git diff --check` прошли.
