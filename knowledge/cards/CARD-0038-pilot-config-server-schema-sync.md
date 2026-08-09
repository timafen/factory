# CARD-0038 — Синхронизировать конфиг пилота со схемой сервера

## HEAD

- Status: specified — план готов к реализации.
- Branch: `factory/79249e81-6cc-316823f3-528`.
- Head commit: `41b6e68` (ревизия спецификации; следующий коммит обновляет
  только эту ссылку в карточке).
- What changes: сервер принимает и без потерь сохраняет `respect_host_load`, а
  эталонный конфиг проверяется строгой серверной схемой.
- Evidence: код сейчас читает флаг в `pilot/pilot.py`, но JSON-тега
  `respect_host_load` нет в `protocol.PilotSettings`; целевой тест описан в
  спецификации.
- Next action: реализовать
  `knowledge/specs/pilot-config-server-schema-sync.md`.

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
