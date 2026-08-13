# CARD-0037 — Мягкий допуск работ при загрузке сервера

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/6b60b7e9-46c-2c414c5b-c50`
- Head commit: `3972208` (`Обновить карточку сохранения отложенной задачи`)
- What changed: при обычной перегрузке допускается один запуск, после чего
  продолжаются только лёгкие стадии; отложенная тяжёлая queued-задача не
  отменяется и будет рассмотрена следующим циклом.
- Evidence: после перебазирования на `origin/main` прошли `python3 -m unittest
  pilot.test_pilot` (32 tests, OK) и `go test ./...` (exit 0); проверены все
  критерии спецификации и чистота диффа из четырёх заявленных файлов.
- Next action: владельцу выполнить merge этой ветки в `main`.

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

### 2026-08-09 — Implement

После разрешения владельца мягкий допуск поставлен в `pilot`: при обычной
перегрузке гарантирован один активный слот, затем запускаются только `Triage`,
`Specification` и `Review`; переполнение памяти или диска остаётся жёсткой
блокировкой. Ранний выход из `cycle` удалён, поэтому сторож и независимые лёгкие
действия продолжаются. Целевые 7 и полные 31 тест пилота прошли; Go-сборка прошла.

### 2026-08-09 — Implement

После возврата из Review проверка допуска перенесена перед `/cancel` в
`rescue_queued`. Теперь перегрузка откладывает перенос тяжёлой стадии, не удаляя
исходную queued-задачу; отдельный регрессионный сценарий проверяет отсутствие
отмены и создания замены. Целевой класс: 8 тестов, OK.

### 2026-08-09 — Verify

| Критерий | Проверка | Наблюдение |
| --- | --- | --- |
| Один гарантированный запуск, затем блокировка тяжёлых | `HostLoadAdmissionTests.test_guaranteed_slot_allows_any_stage`, `test_successful_create_consumes_guaranteed_slot` | первый `Implement + Test` создаётся, второй отклонён до API-вызова |
| Память и диск остаются жёсткой блокировкой | `test_memory_or_disk_emergency_blocks_even_the_guaranteed_slot` | запуск не допускается даже без активных задач |
| Лёгкие стадии продолжаются при одной активной работе | `test_after_guaranteed_slot_only_light_stages_are_allowed` | разрешены `Triage`, `Specification`, `Review` |
| Тяжёлые и неизвестные стадии отложены | `test_after_guaranteed_slot_only_light_stages_are_allowed` | `Implement + Test`, `Verify` и неизвестная стадия не создаются |
| Цикл и queued-задача сохраняют работоспособность | `test_overload_does_not_stop_cycle_services`, `test_overload_defers_rescue_without_cancelling_original` | сторож вызывается; `/cancel` и замена тяжёлой queued-задачи отсутствуют |
| Обычная нагрузка и выключенный предохранитель совместимы | `test_normal_load_or_disabled_guard_preserves_previous_admission` | `Verify` допускается по прежнему правилу |
| Полный набор и смежный Go-код | `python3 -m unittest pilot.test_pilot`; `go test ./...` | 32 tests, OK; exit 0 |

Дифф после перебазирования на свежий `origin/main` содержит только
`knowledge/cards/CARD-0117-server-load-admission.md`,
`knowledge/specs/server-load-admission.md`, `pilot/pilot.py` и
`pilot/test_pilot.py`; `git diff --check origin/main...HEAD` завершился без
замечаний.
