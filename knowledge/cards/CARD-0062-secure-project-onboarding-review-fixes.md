Implementation commit: c9fe387f4b10d5c92d16b071436690324de35ffc — безопасный шаблон проекта, health-подтверждение выпуска и отката, fail-closed production

# CARD-0062 — Безопасное подключение проекта после Review

## HEAD

- Status: READY FOR REVIEW — три замечания Review исправлены и покрыты тестами.
- Branch: `factory/3354b83b-9a8-5c609a06-20e`.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: Factory self-release получает успешный статус только после
  разрешённого health-check; нездоровый выпуск откатывается с повторной проверкой.
  Ручной rollback также проверяет здоровье, клиентский owner-флаг удалён.
- Production: остаётся заблокированным до отдельного серверного одноразового
  подтверждения владельца; клиентское поле `owner_confirmed` отклоняется.
- Evidence: целевые Go-тесты → PASS; Projects UI → 2 PASS; полный Go → PASS;
  полный Web → 14 файлов, 142 теста PASS; vet, lint, typecheck, Go/Web build → PASS.
- One next action: повторить Review трёх исправленных сценариев.

## LOG

### 2026-08-11 — Implement

Работа заново собрана на свежем `origin/main` только из файлов безопасного
подключения проекта. Добавлены health-подтверждение self-release и rollback,
проверяемый откат при нездоровом выпуске и строгий запрет клиентского
`owner_confirmed`. Целевые и полные Go/Web-проверки, vet, lint, typecheck и обе
сборки прошли.
