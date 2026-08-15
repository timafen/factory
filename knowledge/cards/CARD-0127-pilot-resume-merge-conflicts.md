Implementation commit: 0af2d8903a0ad1a194b77942fa219278c418cf27 — AUTO-MERGE получает новый возврат после каждого конфликта

# CARD-0127 — Pilot возвращает конфликт слияния в Implement + Test

## HEAD

Status: Implemented — awaiting Review

Branch: `factory/a4e8042b-cfa-7c84371a-e3b`

Implementation commit: `0af2d8903a0ad1a194b77942fa219278c418cf27` — каждый
AUTO-MERGE-конфликт получает отдельное поколение и новый `merge_conflict_return`.

What changed: Pilot сохраняет счётчик конфликтов и меняет request key после
повторного конфликта, но повторный запуск того же поколения остаётся без дубля.

Evidence: целевые merge-тесты → 11 PASS; полный `pilot.test_pilot` → 310 PASS
(13 skipped); `go test -timeout 5m ./...` и `just build` → PASS.

One next action: Review проверяет повторный проход Implement → Review → Verify.

## LOG

### 2026-08-14 — Specification

Зафиксирован контракт: content conflict не повторяет тот же merge и не создаёт
новую корневую работу. Pilot сохраняет причину, возвращает исходную delivery-
ветку в Implement + Test и допускает новый merge только после новых Review и
Verify.

### 2026-08-14 — Implement

Реализация `12997fa9d6697f24825a7f8b73dad8482e027ebd` закрыла безопасное ожидание
при пустой ветке и любой ошибке маршрута/API. Восемь целевых сценариев
подтвердили durable conflict, exactly-once correction, восстановление после
рестарта, detail API и merge только нового проверенного head. Полный Go-набор,
vet, vulnerability scan, staticcheck, 180 UI-тестов, lint, typecheck, tooling,
launcher и сборка трёх бинарников прошли. Первичный UI-запуск потребовал
штатного `npm ci`; tooling повторён с внешней `FACTORY_BUILD_DIR` снятой.

### 2026-08-14 — Implement

Коммит `0af2d8903a0ad1a194b77942fa219278c418cf27` добавил durable-счётчик
поколения AUTO-MERGE-конфликта: новый конфликт создаёт новый `merge_conflict_return`,
а рестарт того же конфликта сохраняет exactly-once. Целевой набор дал 11 PASS;
полный Pilot — 310 PASS (13 skipped), Go-тесты и изолированная сборка — PASS.
