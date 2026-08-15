Implementation commit: 74ca1989b7e6ef54e04d00fae4192bec43bcae73 — Codex и Claude Code получают единый GH_REPO из origin задачи

# CARD-0300: Рабочий checkout направляет GitHub CLI в origin задачи

## HEAD

Status: Implemented and tested
Branch: factory/34a15183-a8e-f81060ed-2f1
Specification: `knowledge/specs/working-checkout-origin-target-github-repository.md`
What changed: общий конструктор runtime-команды применяет вычисленный из
GitHub.com identity `GH_REPO` и к Codex, и к Claude Code; чужое унаследованное
значение удаляется.
Evidence: 3 целевых теста — PASS; `go test -timeout 5m ./...` — PASS;
`FACTORY_BUILD_DIR=/tmp/card-0300-build just build` — PASS.
One next action: Verify сверяет ветку со свежим remote default branch.

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
