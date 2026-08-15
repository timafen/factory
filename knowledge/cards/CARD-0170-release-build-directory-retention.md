# CARD-0170 — Безопасное удержание каталогов release-сборки

Implementation commit: 12101a9be417202282b8ffab7c981b401322ebf2 — cleanup-fixture отделён от проверки поколений и доступен изолированно.

## HEAD

Status: BLOCKED — полный release-fixture не прошёл старое HUP-ожидание до cleanup.
Branch: factory/e7eed68e-5ce-7d59dc30-a07
Implementation commit: 12101a9be417202282b8ffab7c981b401322ebf2 — cleanup-fixture отделён от проверки поколений и доступен изолированно.
What changed: fixture сохраняет пустой `generations/`, не создавая ложное
непроверенное поколение; cleanup можно проверить режимом `build-cleanup`.
Evidence: `FACTORY_TEST_ONLY=build-cleanup bash ops/test-fx-factory-release.sh` → PASS;
`go test -timeout 5m ./...` и `just build` → PASS; полный release-fixture → FAIL
на прежнем `signal-HUP-1/ui-running` до выполнения cleanup.
Next action: повторить полный release-fixture при свободном хосте и только после PASS сливать.

## LOG

### 2026-08-15 — Implement

Исправлен новый cleanup-fixture: защищённый `generations/` остаётся пустым и
больше не выглядит непроверенным поколением для preflight. Добавлен изолированный
режим `build-cleanup`; он, Go-свита и сборка прошли. Два полных release-прогона
остановились на существующем HUP-таймауте до cleanup при нагрузке хоста выше CPU.

### 2026-08-15 — Implement

Реализованы очистка и dry-run по утверждённой границе CARD-0170. Fixture
подтверждает удаление только старого реального `build-*`, сохранность свежего,
symlink и защищённых префиксов, а также отсутствие gates и сервисных действий в dry-run.
Проверки `bash -n` и `bash ops/test-fx-factory-release.sh` завершились успешно.

### 2026-08-15 — Specification

## Статус

SPECIFIED

## Контекст

В release-каталоге накопились крупные `build-*`. Владелец утвердил очистку
только реальных верхнеуровневых каталогов, созданных штатным
`fx-factory-release`, старше 24 часов и гарантированно не используемых активным
выпуском. `generations/`, `.generation-*` и другие префиксы исключены до
отдельного определения владельца и политики.

## Решение

Под тем же эксклюзивным lock, что и выпуск, скрипт классифицирует только
`build-*`, журналирует решение и удаляет лишь старый проверенный каталог.
`--cleanup-dry-run` выдаёт предварительный список без мутаций и с кодом 0.
Доказательство неактивности штатных каталогов — успешный захват этого lock.

## Граница реализации

- `ops/fx-factory-release`
- `ops/test-fx-factory-release.sh`

Обязательная проверка: `bash ops/test-fx-factory-release.sh`.

## Передача

Следующая стадия реализует спецификацию из
`knowledge/specs/release-build-directory-retention.md`; production-каталоги
вручную не очищать.
