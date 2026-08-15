# CARD-0170 — Безопасное удержание каталогов release-сборки

Implementation commit: 291bf51b5cce52a5884bc8536b829d1f4893822e — полный release-fixture стабильно доказывает очистку и обработку сигналов.

## HEAD

Status: READY — очистка старых build-каталогов и полный release-fixture подтверждены.
Branch: factory/1e2cd568-767-c79d54d1-2c1
Implementation commit: 291bf51b5cce52a5884bc8536b829d1f4893822e — полный release-fixture стабильно доказывает очистку и обработку сигналов.
What changed: release удаляет только старые штатные `build-*`, сохраняя свежие,
symlink и защищённые префиксы; signal-fixture всегда запускает реальный deep gate.
Evidence: `bash ops/test-fx-factory-release.sh` → PASS;
`go test -timeout 5m ./...` → PASS; `just build` → PASS.
Next action: слить ветку в `main`.

## LOG

### 2026-08-15 — Implement

Устранено наследование fast-release в фоновых signal-сценариях, добавлены
ожидание живого gate с диагностикой и корректная смена heartbeat при повторном
rollback-выпуске. Полный release-fixture, Go-свита и сборка завершились PASS;
cleanup удалил старый `build-*` и сохранил все защищённые объекты.

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
