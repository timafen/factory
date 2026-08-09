# CARD-0038 — Синхронизировать конфиг пилота со схемой сервера

## HEAD

- Status: implemented — код и регрессионные проверки готовы к ревью.
- Branch: `factory/20848c54-cb3-6431baf7-158`.
- Head commit: `2e23a41` (проверенная ревизия реализации).
- What changed: серверная схема принимает и сохраняет `respect_host_load`,
  старые конфиги без ключа получают совместимое значение `true`, а эталонный
  конфиг теперь служит входом строгого регрессионного теста.
- Evidence: `go test ./internal/controlplane -run
  TestPilotConfigExampleMatchesServerSchema` → `ok`; `go test ./...` → все
  пакеты `ok`; `go build ./...` → exit 0.
- Next action: провести Review диффа от `origin/main`.

ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/pilot_config.go
ГОТОВО-КОГДА: файл internal/controlplane/pilot_config_test.go
ГОТОВО-КОГДА: файл pilot/config.example.json
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run TestPilotConfigExampleMatchesServerSchema

## LOG

### 2026-08-09 — Specification

Зафиксирован минимальный контракт: добавить уже используемый пилотом флаг в
строгую серверную модель, сохранить совместимый default `true` и поставить
регрессионные ворота на полном репозиторном примере конфигурации. Исходная ветка
принятой спецификации была удалена с `origin`, поэтому документ восстановлен по
актуальному коду на свежем `origin/main`.

### 2026-08-09 — Implement

В строгую модель сервера и эталонный конфиг добавлен `respect_host_load`.
Совместимость старых файлов и сохранение явного `false` закреплены тестом на
полном `pilot/config.example.json`; целевой тест, `go test ./...` и
`go build ./...` завершились успешно. Проверенная ревизия реализации: `2e23a41`.
