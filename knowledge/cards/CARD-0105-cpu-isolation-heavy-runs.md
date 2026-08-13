# CARD-0105 — Изоляция по процессору для тяжёлых прогонов

Implementation commit: c28b5bfc0c5bbb22c7d69d0749c316a2b340841e — базовый код пилота и панели, на который опирается спецификация

## Статус

Specification — готова к реализации.

## Контракт работы

Тяжёлые прогоны ограничиваются CPU и слотами по `work_id`, при этом панель и
Factory Brain остаются обслуживаемыми. Полная спецификация: `knowledge/specs/cpu-isolation-heavy-runs.md`.

## Область реализации

- `pilot/pilot.py`
- `pilot/test_pilot.py`
- `web/src/Overview.tsx`
- `web/src/Overview.test.ts`

## Проверка

После реализации обязательна команда:
`python3 -m unittest pilot.test_pilot && npm --prefix web test -- --run`
