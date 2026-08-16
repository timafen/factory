Implementation commit: отсутствует — этап Specification не изменяет продуктовый код; поле будет заменено полным SHA реализации до следующего документального коммита

# CARD-0175: admission fence для безопасного drain перед выпуском

## HEAD

Status: Specification ready
Branch: factory/85604d3a-09e-2ee7e6f5-550
Related work: штатный выпуск не превращает остановленные им этапы в неудачные работы
Specification: `knowledge/specs/release-drain-admission.md`

## Решение

Выпуск закрывает authoritative admission в control-plane прежде, чем ждёт
обнуления активных этапов и останавливает воркеры. После закрытия новый claim
возвращается пустым и execution остаётся queued; уже выполняемые этапы получают
время на завершение. При timeout или ошибке до stop admission открывается снова;
после успешного запуска — только после проверки здорового runtime.

## Границы

В области: protocol/control-plane claim fence, локальный защищённый release API,
порядок `fx-factory-release`, worker-обработка пустого claim и детерминированные
Go/shell-регрессии.

Вне области: UI, ручное оживление работ, изменение retry-политик и изменение
семантики настоящих отмен, таймаутов или ошибок задач.

## Доказательство, которое обязан дать Implement

- Гонка между последним нулевым drain и `stop factory-worker` не создаёт
  попытку и не добавляет `failed` в историю работы.
- Drain timeout не останавливает воркеры и вновь открывает admission.
- Обычные `cancelled`, timeout и реальные `failed` не получают release-retry.
- `bash ops/test-fx-factory-release.sh` и новый целевой Go-тест завершаются
  кодом 0.

## Следующее действие

Реализовать contract и fence по спецификации, сначала сделать отдельный commit
с кодом и тестами, затем заменить первую строку этой карточки его полным SHA и
человеческим описанием.
