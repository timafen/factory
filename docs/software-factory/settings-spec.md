# Экран «Настройки» для фабрики

## Цель

Оператор видит и безопасно меняет `pilot/config.json` из control-plane на
странице `/settings`. Pilot перечитывает этот файл в начале каждого цикла,
поэтому сохранённые значения применяются не позднее следующего polling cycle.
Настройки сервера, worker-процессов и провайдеров не входят в этот экран.

## Контракт

Control-plane использует `<FACTORY_DATA_HOME>/pilot/config.json` и публикует:

- `GET /api/v1/settings/pilot` — настройки, SHA-256 версию и предупреждения;
- `PUT /api/v1/settings/pilot` — полную схему и версию из GET.

PUT проверяет схему и значения, записывает временный файл в том же каталоге,
выполняет `fsync` и atomic rename. Устаревшая версия получает
`409 config_conflict`. Missing, symlink, oversized и испорченный файл дают
предсказуемую API-ошибку и не заменяются.

Поддерживаются операционные флаги и интервалы, маршрутизация пяти стадий по
tiers `low`/`medium`/`high`, бюджеты, автоматизации, уведомления, ссылки,
`stopped_pipelines`, `skip_stages_for_low` и упорядоченный `brain_chain`.
Верхнеуровневый `_note` и `brain_chain[].note` сохраняются; неизвестные поля
отклоняются.

## Источник worker ID

Отдельного реестра не создаётся. При первом сохранении `allowed_workers`
инициализируется из ID исполнителей, уже известных control-plane на этот
момент. После этого список хранится в `pilot/config.json` и редактируется на
экране. Для старого файла без политики действует `allow_any_worker=true`, так
что обновление не меняет прежнее поведение фабрики само по себе.

При `allow_any_worker=false` worker вне `allowed_workers` блокирует сохранение.
При `true` он сохраняется, но GET/PUT и экран показывают предупреждение.

## Проверка значений

Обязательны ровно стадии `Triage`, `Specification`, `Implement + Test`,
`Review`, `Verify` и все три tier-а. Секунды, попытки, параллельность, денежные
лимиты и коэффициенты конечны и положительны. URL имеют схему `http`/`https`.
`brain_chain` не пуст, каждая строка содержит `cli`, `model`, `provider`.

## Критерии приёмки

1. `/settings` показывает и позволяет менять всю схему, включая notes и
   порядок brain chain.
2. Допустимое сохранение атомарно заменяет файл и возвращает новую версию.
3. Неполная/невалидная схема не меняет файл и даёт понятную ошибку.
4. Worker policy работает в строгом режиме и с предупреждениями в мягком.
5. Устаревшее сохранение получает 409 и экран предлагает обновить данные.
6. Ошибки файла безопасны и не повреждают прежнее содержимое.

## Вне области

Аутентификация control-plane, изменение кода pilot для общего file lock и
редактирование server/worker/provider settings этой задачей не добавляются.

## Проверяемые обещания

Карточка работы: `knowledge/cards/CARD-0064-settings-spec-verifiable-promises.md`.

ГОТОВО-КОГДА: файл `internal/protocol/types.go`
ГОТОВО-КОГДА: файл `internal/controlplane/http.go`
ГОТОВО-КОГДА: файл `internal/controlplane/pilot_config.go`
ГОТОВО-КОГДА: файл `internal/controlplane/pilot_config_http.go`
ГОТОВО-КОГДА: файл `internal/controlplane/pilot_config_test.go`
ГОТОВО-КОГДА: файл `cmd/factory-server/main.go`
ГОТОВО-КОГДА: файл `web/src/App.tsx`
ГОТОВО-КОГДА: файл `web/src/Settings.tsx`
ГОТОВО-КОГДА: файл `web/src/Settings.test.tsx`
ГОТОВО-КОГДА: файл `web/src/api.ts`
ГОТОВО-КОГДА: файл `web/src/types.ts`
ГОТОВО-КОГДА: файл `web/src/styles.css`
ГОТОВО-КОГДА: файл `web/e2e/control-plane.spec.ts`
ГОТОВО-КОГДА: файл `web/e2e/server.mjs`
ГОТОВО-КОГДА: команда `go test ./internal/controlplane -run 'TestPilotConfigStorePreservesNotesAndRejectsConflict|TestPilotConfigValidationWorkerPolicy|TestPilotSettingsHTTPInitializesKnownWorkerIDsAndConflicts' -count=1`
