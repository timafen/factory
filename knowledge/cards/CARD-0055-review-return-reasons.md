# CARD-0055 — Повторяющиеся причины возвратов Review

## HEAD

Status: Implemented — ожидает Review.
Branch: `factory/38bc9eef-27e-896afde8-71f`.
Implementation commit: d2e9dcc5329b4472a45bf7e26b6b82df7a84e2ec — сохранение и показ причин возврата Review.
What changed: Pilot строго принимает семь причин и пишет идемпотентный журнал;
метрика и «Главное» показывают счётчики, доли и исторические возвраты как
«не классифицировано».
Evidence: `python3 -m unittest pilot.test_pilot` → 156 OK; `go test
./internal/controlplane -run 'Efficiency'` → OK; `npm --prefix web test --
--run src/Overview.test.ts` → 14 passed.
Next action: Review проверить маршрутизацию возврата и экран «Главное».

## LOG

### 2026-08-10 — Implement

Введён строгий контракт причины для `REQUEST CHANGES`, журнал без дублей и
агрегация причин по влитым работам; интерфейс выводит число и долю или пустое
состояние. Целевые Python, Go и web-проверки прошли.

### 2026-08-10 — Specification

Проверены текущие `pilot/pilot.py`, `internal/controlplane/efficiency.go` и
`web/src/Overview.tsx`. Review сейчас возвращает работу по неструктурированному
результату, а «Главное» показывает лишь долю первого прохождения. Спецификация
закрепляет обязательную явную категорию, журнал возвратов, честную метку старых
данных «Не классифицировано» и отображение агрегата на существующем экране
эффективности.
