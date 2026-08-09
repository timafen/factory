# CARD-0037 — Мягкий допуск работ при загрузке сервера

## HEAD

- Status: Implement complete — awaiting Verify
- Branch: `factory/3e984ded-44a-8141732d-17a`
- Head commit: `4368da8` (`Сохранить движение лёгких этапов при загрузке сервера`)
- What changed: при обычной перегрузке пилот сохраняет один гарантированный запуск,
  пропускает `Triage`, `Specification`, `Review` и откладывает тяжёлые стадии.
  Авария памяти или диска остаётся полной блокировкой.
- Evidence: `python3 -m unittest pilot.test_pilot.HostLoadAdmissionTests` → 7 tests, OK;
  `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → exit 0;
  `go build ./...` → exit 0.
- Next action: Verify прогоняет полный `python3 -m unittest pilot.test_pilot`.

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
