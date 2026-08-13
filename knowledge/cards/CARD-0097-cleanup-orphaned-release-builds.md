# CARD-0097 — Осиротевшие папки release-сборок освобождают место безопасно

Implementation commit: d260745be36307ce0d31fdbafef77555951c530f — определена проверяемая реализация безопасной очистки осиротевших release-сборок до нового выпуска.

## HEAD

- Status: Specification — ready for Implement.
- Branch: `factory/7b562197-269-1774d4d3-4b3`.
- Specification: `knowledge/specs/cleanup-orphaned-release-builds.md`.
- Owner impact: следующий выпуск освобождает место от оборванных `build-*`, не
  затрагивая поколения и чужие данные.
- Scope: только `ops/fx-factory-release` и `ops/test-fx-factory-release.sh`;
  ручная production-очистка и остальные имена вне scope.
- One next action: Implement добавляет узкую cleanup-проверку и fixture-сценарий.

## LOG

### 2026-08-12 — Specification

Фактический release-скрипт захватывает lock до создания `$REL/build-XXXXXX`,
а retention обходит только `$REL/generations`. Поэтому очистка назначена строго
между lock/подготовкой `$REL` и `mktemp`: она принимает лишь реальный
непосредственный каталог `build-*` внутри канонического `$REL`, отклоняет
symlink и внешний путь, сохраняет все иные имена. Обязательная проверка —
`bash ops/test-fx-factory-release.sh` с marker-сценарием осиротевшей папки,
чужой папкой и внешним target symlink.
