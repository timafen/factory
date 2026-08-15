Implementation commit: pending — спецификация текущей работы; продуктовый код на этапе Specification не изменяется

# CARD-0302: pre-start release failure is not rollback failure

Status: Specified
Specification: `knowledge/specs/prestart-release-failure-not-rollback.md`

## Контекст

Определённый отказ POST broker до запуска операции сейчас сохраняется как
`rollback_failed` в `internal/controlplane/project_adapters.go`. В
`internal/releasebroker/broker.go` невозможность `command.Start()` также
возвращает `rollback_failed`. Оба случая не подтверждают изменение сервера и
не требуют заявления о неудавшемся откате.

## Ожидаемый результат

Операция получает durable `failed` с честным pre-start сообщением. Статусы
`release_failed_rolled_back`, `health_failed_rolled_back` и настоящий
`rollback_failed` сохраняют прежнюю семантику. API и Projects принимают и
показывают новый статус.

## Проверка

Обязательная проверка и полный список файлов реализации находятся в
спецификации. Реализация, тестовый commit и их SHA будут добавлены на следующем
этапе; эта карточка не изменяет общие журналы и карточки других работ.
