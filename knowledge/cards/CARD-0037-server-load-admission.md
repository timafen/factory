# CARD-0037 — Мягкий допуск работ при загрузке сервера

## HEAD

- Status: Specification complete — implementation remains open
- Branch: `factory/69b852f2-6fb-8a930395-255`
- Head commit: `7cfef92` (`Оставить поставку мягкого допуска в заявленной области`)
- What changed: из поставки убраны незаявленные изменения `pilot/*`;
  критерии готовности спецификации приведены к разрешённой области.
- Evidence: `git diff --exit-code origin/main -- pilot/pilot.py pilot/test_pilot.py` → exit 0;
  `git diff --name-only origin/main...HEAD` → только карточка и спецификация;
  `python3 -m unittest pilot.test_pilot` → 24 tests, OK; `go build ./...` → exit 0.
- Next action: согласовать расширение области на `pilot/pilot.py` и `pilot/test_pilot.py` для реализации.

## LOG

### 2026-08-09 — Specification

Текущее поведение подтверждено в `pilot/pilot.py`: `cycle` безусловно завершает
итерацию при `host_overloaded`, до сторожа и переходов конвейера. Согласован
минимальный объём без новых API и настроек: единая проверка допуска сохраняет
одну работу и лёгкие стадии, а `Implement + Test` и `Verify` ждут снижения
нагрузки. Подробный контракт — в `knowledge/specs/server-load-admission.md`.

### 2026-08-09 — Implement

Единый допуск встроен перед `create_task`, поэтому применяется к переходам,
ответам владельца, сторожу, эпикам и автозапуску без дублирования политики.
Целевой класс: 7 тестов, OK; соседний `CreateTaskFallbackTest`: 1 тест, OK;
компиляция `pilot/pilot.py` и `pilot/test_pilot.py`: exit 0; `go build ./...`: exit 0.

### 2026-08-09 — Implement

По результату машинной проверки из ветки убраны изменения `pilot/pilot.py`
и `pilot/test_pilot.py`, не входившие в заявленную область. Итоговый дифф от
точки ветвления содержит только карточку и спецификацию; целевая проверка чистоты
`pilot/*` завершилась с exit 0. Реализация политики в этой области не поставляется.
