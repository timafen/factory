# CARD-0097 — Неизменяемый снимок состава тупиков и причины архивирования

Implementation commit: 2cacc50ec06bacb069c53179f1cdb96871aed84b — предыдущая
принятая code-работа уже присутствует в ancestry этой ветки; продуктовая
реализация CARD-0097 планируется следующим этапом.

## HEAD

- Status: Specification — awaiting implementation.
- Branch: `factory/4587fd9a-021-c4edfe81-188`.
- Specification: `knowledge/specs/dead-end-work-snapshot-and-archive-reasons.md`.
- Owner decision: обязательный текущий контур — 73 работы; 74 — первоначальная
  скользящая метрика, пропавшая работа неидентифицируема.
- Scope: snapshot полного состава, digest, пагинация свыше 100, reason-коды
  архивирования и связь с efficiency; UI и продуктовые правила не меняются.
- Evidence at Specification: код `pilot/pilot.py` ограничен
  `/tasks?limit=100`, а `efficiency.go` считает терминальные хвосты без
  immutable source snapshot.

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
