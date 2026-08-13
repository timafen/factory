# Экран «Автоматизация»: все автоматики Фабрики с живым статусом

## Цель и влияние на владельца

Владелец видит на одном экране не только сохранённые Automation control plane,
но и все обслуживающие Фабрику автоматики: управляющие процессы, службы
выката, pilot-патрули и janitor. У каждой строки есть понятные название,
назначение, текущее состояние и время последней активности. Это позволяет
сразу отличить остановленную или недоступную автоматику от работающей, не
искать журналы и systemd вручную.

«Нет данных» — самостоятельное честное состояние: оно показывается, когда
адаптер источника недоступен либо время последнего запуска отсутствует. Оно
никогда не преобразуется в «работает» или «здорово».

## Технический подход и реальные файлы

1. В `internal/protocol/types.go` появится отдельная read-only нормализованная
   модель статуса: стабильный source/id, category, title, purpose, status,
   last_activity_at и data_status/diagnostic. Она не расширяет mutable
   `Automation` и не выдаёт host-команды в браузер.
2. `internal/controlplane/automation_status.go` введёт адаптеры с единым
   контрактом. Адаптер durable Automations читает текущие `Automation`,
   `Health`, `LatestRun` и `LastCheckedAt` из `Store`. Адаптер host-снимка
   читает атомарный файл, подготовленный pilot: он содержит только allowlist
   `factory-pilot`, `factory-release-broker`, известные release-службы и
   `factory-janitor`, их назначение, systemd ActiveState и метку последнего
   события. Нормализация сортирует строки детерминированно и сохраняет строку
   источника при его ошибке, помечая её «нет данных».
3. `pilot/pilot.py` на каждом цикле будет обновлять отдельный атомарный
   `automation-status.json` рядом с уже существующим `dashboard.json`.
   Он берёт состояние только у известных unit через безопасный фиксированный
   вызов `systemctl show`; последнюю активность pilot — из завершённого цикла,
   janitor — из последней датированной записи
   `/var/log/factory-janitor.log`, а release-служб — из systemd timestamp.
   Неуспех одной команды, отсутствие unit, журнала или валидной метки оставит
   соответствующую запись с `data_status=no_data`; прочие источники останутся
   видимыми. Не передавать в этот файл произвольные строки журналов, секреты
   или аргументы ExecStart.
4. `internal/controlplane/automations_status_http.go` добавит
   `GET /api/v1/automations/status`, а `internal/controlplane/http.go`
   зарегистрирует маршрут. Текущий `GET /api/v1/automations` сохранит
   pagination и существующий CRUD-контракт, чтобы формы и detail-экран не
   изменились.
5. `web/src/types.ts` и `web/src/api.ts` опишут и получат новый список.
   `web/src/Automations.tsx` заменит верхнюю таблицу на единый read-only
   список статусов, обновляемый тем же visible polling. Строка показывает
   название, назначение, состояние и «Последняя активность: нет данных» при
   отсутствии timestamp; editable Automation остаётся кликабельной и ведёт
   в прежнюю детальную карточку, host-строки не предлагают операций создания,
   включения или запуска. Фильтры адаптируются к category/status, а создание
   и миграция остаются в панели control plane.
6. `internal/controlplane/automation_status_test.go` проверит объединение,
   дедупликацию и отказ одного адаптера; `pilot/test_pilot.py` — снимок и
   случаи отсутствующих systemd/janitor данных; `web/src/Automations.test.tsx`
   — владелец видит все категории и честную подпись «нет данных».

Реальные уже существующие источники: durable таблицы Automations и occurrences
в `internal/controlplane/automations.go`; pilot (`pilot/pilot.py` и
`ops/systemd/factory-pilot.service`); release broker
(`ops/systemd/factory-release-broker.service`); janitor
(`ops/factory-janitor.sh`). Набор host-служб определяется allowlist в коде, а
не результатом широкого `systemctl list-units`, чтобы случайные процессы не
попали на экран.

## Последовательный план

1. Зафиксировать protocol-модель, перечисление категорий и правило «нет
   данных», затем написать unit-тесты adapters с поддельными Store и
   snapshot-reader.
2. Реализовать подготовку пилотного snapshot: allowlist, parsing timestamps,
   атомарная запись, ограничение диагностики и изоляция ошибок источников.
3. Собрать control-plane adapters и новый read-only endpoint, не меняя
   семантику существующего списка Automations.
4. Перевести API и экран на нормализованный список, сохранив detail и
   управляющие действия только для durable Automation.
5. Запустить целевые Go, Python и UI-тесты; при доступном стенде открыть
   `/automations` и сверить все категории и «нет данных» глазами.

## Критерии приёмки

- Новый `GET /api/v1/automations/status` возвращает единый read-only список:
  как минимум одну строку durable Automation и по одной строке pilot,
  release broker, известной службы выката и janitor; строка не пропадает,
  если её источник недоступен, а получает `data_status=no_data`.
- `/automations` одновременно показывает control-plane Automation, pilot,
  службы выката и janitor как нормализованные строки.
- Каждая строка содержит название, назначение, состояние и время последней
  активности либо дословно «нет данных».
- Недоступный systemd, отсутствующий журнал или неразбираемая дата не
  скрывают строку и не делают её работающей; остальные строки продолжают
  обновляться.
- Статус durable Automation согласован с её health/последним occurrence, а
  переход к существующему detail и все текущие CRUD-действия работают как
  прежде.
- Никакие shell-команды, секреты, ExecStart, полные журналы и произвольные
  host-unit не попадают в HTTP-ответ или UI.
- Список обновляется в видимой вкладке без ручной перезагрузки и остаётся
  читаемым при частичном отказе источника.

## Тест-план

- `go test ./internal/controlplane -run 'TestAutomationStatus'`: fixture
  durable Automation + host snapshot даёт все категории, устойчивую сортировку
  и корректную last activity; ошибки/пустые timestamps дают `no_data`.
- `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests`:
  allowlist, timestamp из janitor и systemd, атомарный файл и частичный отказ
  без ложного `running`.
- `cd web && npm test -- --run web/src/Automations.test.tsx`: таблица выводит
  все типы и «нет данных», а host-строка не получает control-plane action.
- После реализации выполнить `go test ./internal/controlplane -run
  'TestAutomationStatus'` как обязательную быструю регрессию; общая Verify
  стадия отдельно запускает полный набор.

## Риски и решения

| Риск | Решение |
| --- | --- |
| У server нет прав читать systemd/journal | Снимок собирает уже установленный pilot; endpoint только читает файл. Отсутствие прав — `no_data`, не 500. |
| Логи janitor не содержат надёжной даты | Парсить только ISO-дату, иначе показывать «нет данных»; не использовать mtime как подмену запуска. |
| Host-инвентаризация выдаст лишние/чувствительные службы | Жёсткий versioned allowlist и минимальный DTO без команд и журнала. |
| Новый endpoint сломает редактирование Automation | Не менять `/api/v1/automations`; UI сохраняет существующий detail для durable строк. |
| Источник зависнет и замедлит экран | Snapshot готовится вне HTTP на цикле pilot; endpoint читает один ограниченный файл. |

## Карточка работы

Карточка: `knowledge/cards/CARD-0119-automation-live-status.md`.

Статус: Specification. Реализация должна сделать единственный нормализованный
read-only список со снимком host-источников и без ложного здоровья при
отсутствии данных.

ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_status.go
ГОТОВО-КОГДА: файл internal/controlplane/automations_status_http.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_status_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/api.ts
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/Automations.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestAutomationStatus'
