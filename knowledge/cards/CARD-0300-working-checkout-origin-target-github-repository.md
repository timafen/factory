# CARD-0300: Рабочий checkout направляет GitHub CLI в origin задачи

## HEAD

Status: Implemented and tested
Implementation commit: c0dbe1c2d89be440b48aa3f9b2019613b33b28d4 — Codex и Claude Code получают единый GH_REPO из origin задачи
Branch: factory/80ab804a-2dc-a4c9d49b-962
Specification: `knowledge/specs/working-checkout-origin-target-github-repository.md`
What changed: общий конструктор runtime-команды применяет вычисленный из
GitHub.com identity `GH_REPO` и к Codex, и к Claude Code; чужое унаследованное
значение удаляется.
Evidence: 3 целевых теста, `go test -count=1 ./...`, `go build ./...` и
`npx tsc -p tsconfig.app.json --noEmit` — PASS.
One next action: Verify сравнивает ветку со свежим remote default branch и
проверяет опубликованный SHA.

## LOG

### 2026-08-15 — Specification

Зафиксирован контракт для наблюдаемого checkout с
`origin=timafen/factory` и `upstream=owainlewis/factory`: runtime должен
экспортировать `GH_REPO=timafen/factory` из repository identity задачи, а не
полагаться на выбор GitHub CLI по remote-ам. Для невалидных и недоверенных
identity переменная удаляется целиком.

`CARD-0300` и этот путь проверены как отсутствующие в свежем `origin/main` и
во всех опубликованных refs `origin`; существующие карточки другой работы не
изменялись.

### 2026-08-15 — Implement

Команда Codex и Claude Code теперь создаётся через общий конструктор,
применяющий одну политику `GH_REPO` из repository identity задачи. Табличный
unit-тест подтвердил нормализацию и отрицательную матрицу, новый тест — оба
runtime, сквозной worker-тест — полный путь claim → supervisor → fake Codex.
Полный Go-набор и сборка трёх исполняемых файлов завершились успешно.

### 2026-08-15 — Implement

Возобновлённая стадия подтвердила реализацию в свежем `origin/main`; указанный
старый ref исполнителя отсутствует на origin, поэтому чужие коммиты не копировались.
Целевые worker-тесты, полный Go-набор, `go build ./...` и TypeScript-проверка
`web` завершились успешно.
