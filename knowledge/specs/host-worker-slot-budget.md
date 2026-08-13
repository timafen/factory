# Спецификация: общий бюджет worker-слотов по числу ядер

## Цель и влияние на владельца

На узле с 8 логическими CPU все worker-службы суммарно получают не более 8
непросроченных задач. Локальный `max_concurrent` остаётся защитой отдельного
worker, но не должен позволять нескольким службам перегрузить машину.
Настраиваемый предел в эту работу не входит: источник истины — `runtime.NumCPU()`.

## Технический подход и реальные файлы

В `internal/controlplane/state.go` добавить admission-check в существующую
транзакцию `Claim`: посчитать по всем worker активные `preparing` и `running`
attempts с неистёкшим lease; при достижении `runtime.NumCPU()` вернуть пустой
claim без создания attempt. SQLite immediate transaction сериализует гонку за
последний слот. `internal/controlplane/store.go` хранит вычисленный предел;
`internal/controlplane/store_test.go` выражает регрессию. Документация обновляется
в `docs/worker.md` и `docs/local.md`.

Реальные файлы реализации: `internal/controlplane/state.go`,
`internal/controlplane/store.go`, `internal/controlplane/store_test.go`,
`docs/worker.md`, `docs/local.md`. UI, схема БД и wire-контракт не меняются.

## Последовательный план

1. Инициализировать лимит числом логических CPU при открытии control plane.
2. Проверять общий бюджет внутри атомарного `Claim`, сохранив локальный лимит.
3. Учесть освобождение terminal-состоянием и истечением lease.
4. Добавить тест восьми успешных claim и пустого девятого, включая конкуренцию.
5. Обновить операторскую документацию и выполнить целевую проверку.

## Критерии приёмки

1. Два worker с локальным пределом 10 на 8-ядерном узле суммарно создают 8
   active attempts; девятый claim пуст и attempt не создаётся.
2. Параллельная выдача последнего слота не превышает 8; повтор идемпотентного
   request возвращает уже выданную попытку.
3. Завершение или истечение lease освобождает слот; `preparing` учитывается.
4. Поведение определяется `runtime.NumCPU()`, без конфигурационного override.

## Тест-план

- `go test ./internal/controlplane -run '^TestClaimEnforcesHostMaxConcurrentAcrossWorkers$' -count=1`.
- Проверить конкурентную границу, replay, terminal transition и lease expiry в
  целевых store-тестах.
- Выполнить `go test ./...`, `go build ./...` и `git diff --check` на этапе Verify.

## Риски и решения

- Гонка за последний слот устраняется существующей immediate SQLite-транзакцией.
- Устаревшие lease не блокируют ёмкость: учитываются только непросроченные строки.
- Расхождение с CARD-0094: там описан `host_max_concurrent` override; утверждённый
  текущей задачей контракт проще и намеренно использует только `runtime.NumCPU()`.
- Удалённый fleet не входит в область: один Store соответствует одному узлу.

## Карточка работы

`knowledge/cards/CARD-0098-host-worker-slot-budget.md` — существующая карточка
этой работы, перенесённая без создания дубликата.

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл docs/worker.md
ГОТОВО-КОГДА: файл docs/local.md
ГОТОВО-КОГДА: команда test "$(go test ./internal/controlplane -list '^TestClaimEnforcesHostMaxConcurrentAcrossWorkers$' | grep -c '^TestClaimEnforcesHostMaxConcurrentAcrossWorkers$')" -eq 1 && go test ./internal/controlplane -run '^TestClaimEnforcesHostMaxConcurrentAcrossWorkers$' -count=1
