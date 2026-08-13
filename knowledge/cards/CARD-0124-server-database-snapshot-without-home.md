# Сервер создаёт снимок базы без домашней папки

Implementation commit: 3090866634059f02a6fc5ae5d2ada869e1662a97 — явный CLI backup обходит вычисление домашней папки и чтение bootstrap.

## HEAD

Status: Specification ready — duplicate routed to the existing candidate.

Spec: `knowledge/specs/server-database-snapshot-without-home.md`.

Candidate branch: `factory/7276dbb0-e0b-afc197a8-73b`.

What changes: `factory-server -database SOURCE -backup DEST` создаёт снимок до
поиска домашней папки. Обычный запуск и остальные recovery-режимы продолжают
загружать прежние defaults и bootstrap.

Owner decision: проверить и включить существующий кандидат, не создавать новое
решение; после PASS выполнить squash-слияние в `main`, без живого выката.

One next action: Review существующего кандидата относительно свежего remote
default branch по критериям спецификации.

## LOG

### 2026-08-13 — Specification

- Подтверждено, что текущий `run()` вызывает `defaultDatabasePath()` до разбора
  `-database` и `-backup`, поэтому явный backup всё ещё зависит от `HOME`.
- Свежий remote `main` зафиксирован на
  `73f4edce272cb113607540412425d842158e2b81`, кандидат — на
  `749305c6d9bf2f7d3cd4306a638adbc73397f3d6`.
- Трёхточечное сравнение показывает только `cmd/factory-server/main.go`,
  `cmd/factory-server/main_test.go` и эту карточку; коммит реализации входит в
  историю кандидата.
- Спецификация требует subprocess-регрессию без домашних переменных, четыре
  формы флагов, автономность снимка и неизменность источника.
- Работа признана точным дубликатом этой карточки; новый дизайн исключён.

### 2026-08-13 — Предыдущее Verify кандидата

- Целевой `go test -count=1 ./cmd/factory-server` и `go build ./...` прошли.
- Subprocess-проверка покрыла четыре формы CLI без `HOME`, автономность снимка
  и неизменность источника.
- Ранее полный набор зависал в незатронутых `internal/controlplane` и
  `internal/worker`; перед слиянием Verify должен повторить полный прогон один
  раз на свежей базе.
