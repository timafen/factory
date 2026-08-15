# CARD-0170 — Безопасное удержание каталогов release-сборки

Implementation commit: 5c3434fdfd6fe4647bc6e9f4d412d6f47e6dd65b — безопасная очистка старых верхнеуровневых `build-*` до новой сборки.

## HEAD

Status: IMPLEMENTED
Branch: factory/a83fc90f-150-892fa826-5a4
Implementation commit: 5c3434fdfd6fe4647bc6e9f4d412d6f47e6dd65b — безопасная очистка старых верхнеуровневых `build-*` до новой сборки.
What changed: release под lock удаляет лишь реальные `build-*` старше 24 часов;
`--cleanup-dry-run` журналирует решения, не создавая выпуск.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` → PASS;
`bash ops/test-fx-factory-release.sh` → PASS.
Next action: провести review изменений перед слиянием.

## LOG

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
