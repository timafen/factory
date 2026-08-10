# CARD-0047 — UTF-8 для текста задач и коммитов воркера

## HEAD

- Status: Implement — готово к проверке.
- Branch: `factory/6683ea14-a5e-082c08e2-527`.
- Head commit: `43ca115` — runtime запускается с `LANG` и `LC_ALL` равными
  `C.UTF-8`, сохраняя остальные переменные среды.
- What changed: добавлена регрессия с исходной ASCII-locale; она проверяет
  точные русские prompt, результат runtime и subject Git-коммита.
- Evidence: `go test ./internal/worker -run TestSupervisorPreservesCyrillicWithUTF8RuntimeLocale -count=1` → PASS;
  `go test ./internal/worker` → PASS.
- One next action: Review проверяет ограниченный diff и целевой тест.

## LOG

### 2026-08-10 — Specification

Исходная ветка принятой спецификации `factory/6a183d47-b4b-ca2ee1bf-d1f`
больше не доступна на `origin`, поэтому документ восстановлен по актуальному
коду на свежем `main`. Область намеренно ограничена запуском runtime-процесса:
форматы задач, HTTP API, база данных и интерфейс уже передают строки как UTF-8
и не требуют изменений.

### 2026-08-10 — Implement

`superviseRuntime` теперь передаёт Codex и Claude Code окружение с явными
`LANG=C.UTF-8` и `LC_ALL=C.UTF-8`, не отбрасывая прочие переменные. Регрессия
запускает supervisor при `LANG=C` и `LC_ALL=C`, затем подтверждает точное
сохранение русских prompt, runtime-результата и subject Git-коммита.
Проверки: целевой `go test ./internal/worker -run TestSupervisorPreservesCyrillicWithUTF8RuntimeLocale -count=1` и полный пакет `go test ./internal/worker` прошли.
