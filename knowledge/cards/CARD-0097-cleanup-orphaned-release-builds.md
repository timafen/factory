# CARD-0097 — Осиротевшие папки release-сборок освобождают место безопасно

Implementation commit: 1d79a563c99c1d2d53eab68d4a2dd965007be2c6 — выпуск безопасно удаляет осиротевшие каталоги build-* до новой сборки.

## HEAD

- Status: Implement — complete, проверено, готово к вливанию.
- Branch: `factory/db86ddee-ec7-d45dcede-582`.
- Specification: `knowledge/specs/cleanup-orphaned-release-builds.md`.
- What changed: после release lock выпуск удаляет только реальные верхнеуровневые
  `build-*`; symlink, внешний target и остальные имена сохраняются.
- Evidence: `bash -n` и `bash ops/test-fx-factory-release.sh` — PASS;
  `FACTORY_BUILD_DIR=/tmp/card-0097-build just build` — PASS.
- Known baseline: на свежем `origin/main` `just check` воспроизводит SA4000 в
  `internal/worker/attempt_lifecycle_test.go:31`; это вне области работы.
- One next action: влить проверенное изменение в main.

## LOG

### 2026-08-12 — Specification

Фактический release-скрипт захватывает lock до создания `$REL/build-XXXXXX`,
а retention обходит только `$REL/generations`. Поэтому очистка назначена строго
между lock/подготовкой `$REL` и `mktemp`: она принимает лишь реальный
непосредственный каталог `build-*` внутри канонического `$REL`, отклоняет
symlink и внешний путь, сохраняет все иные имена. Обязательная проверка —
`bash ops/test-fx-factory-release.sh` с marker-сценарием осиротевшей папки,
чужой папкой и внешним target symlink.

### 2026-08-12 — Implement

После захвата release lock добавлена очистка только проверенных реальных
верхнеуровневых каталогов `build-*`; symlink и кандидаты вне канонического
release-каталога пропускаются. Fixture подтверждает удаление marker осиротевшей
сборки, сохранность чужой папки, symlink и внешнего target, а также успешную
публикацию поколения. `bash -n` и целевой release fixture прошли; сборка трёх
бинарников прошла. Общий `just check` выявил прежний SA4000 вне области задачи.

### 2026-08-12 — Verify

Проверен diff от свежего `origin/main`: изменения ограничены release-очисткой,
её fixture и документацией. `bash -n`, полный целевой fixture и сборка трёх
бинарников прошли. В отдельной свежей копии `origin/main` `just check`
воспроизводит SA4000 в `internal/worker/attempt_lifecycle_test.go:31`, поэтому
это подтверждённый базовый долг вне CARD-0097.
