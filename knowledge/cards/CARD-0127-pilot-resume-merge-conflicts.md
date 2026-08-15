Implementation commit: 12997fa9d6697f24825a7f8b73dad8482e027ebd — Pilot безопасно возвращает конфликт слияния той же работе в Implement + Test

# CARD-0127 — Pilot возвращает конфликт слияния в Implement + Test

## HEAD

Status: Implemented — awaiting Review

Branch: `factory/1757d892-437-271a7c4a-b84`

What changed: конфликт GitHub остаётся durable intent и создаёт ровно одну
correction-задачу на исходной ветке. Пустая ветка, недоступный маршрут или
ошибка Control Plane теперь безопасно ждут следующего цикла.

Evidence: `MergeConflictRecoveryTests` → 8 PASS; полный Go-набор, vet,
vulnerability scan и staticcheck → PASS; UI → 180 PASS, lint/typecheck → PASS;
tooling, launcher и сборка трёх бинарников → PASS.

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
