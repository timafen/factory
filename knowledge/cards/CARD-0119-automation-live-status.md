# CARD-0119: единый живой статус автоматик Фабрики

Implementation commit: 2d59cb736f808dfcec1bc3dfbecda0d873cf2c3b — определён контракт единого списка автоматик, адаптеры источников и целевая проверка.

## HEAD

Status: Specification — ready for implementation.

What changed: зафиксирована поставка, в которой экран «Автоматизация» объединяет durable Automation control plane, pilot, службы выката и janitor через адаптеры к существующим источникам. Для каждого источника определены название, назначение, состояние, последняя активность и обязательное честное «нет данных».

Evidence: изучены текущий API списка (`internal/controlplane/automations_http.go`), durable Store (`internal/controlplane/automations.go`), экран (`web/src/Automations.tsx`), pilot snapshot (`pilot/pilot.py`), release broker и janitor. Номер и путь карточки свободны в свежем `origin/main` и опубликованных ветках.

One next action: Implement создаёт нормализованный read-only endpoint, snapshot host-источников, UI и целевые тесты из `knowledge/specs/automation-live-status.md`.

## LOG

### 2026-08-13 — Specification

Утверждена полная граница: показываются все автоматики Фабрики, включая
управляющую систему, службы выката, pilot-патрули и janitor. Существующий
список содержит только control-plane Automation, поэтому новая поставка
сохраняет его CRUD-контракт и добавляет отдельный нормализованный read-only
статус со снимком host-источников. Недоступность журнала или службы остаётся
видимой как «нет данных» и не маскируется здоровым состоянием.
