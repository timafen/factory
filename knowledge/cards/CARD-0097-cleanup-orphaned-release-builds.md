# CARD-0097 — Осиротевшие папки release-сборок освобождают место безопасно

Implementation commit: 1d79a563c99c1d2d53eab68d4a2dd965007be2c6 — выпуск безопасно удаляет осиротевшие каталоги build-* до новой сборки.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/db86ddee-ec7-d45dcede-582`.
- Specification: `knowledge/specs/cleanup-orphaned-release-builds.md`.
- What changed: после release lock выпуск удаляет только реальные верхнеуровневые
  `build-*`; symlink, внешний target и остальные имена сохраняются.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` — PASS;
  `FACTORY_RELEASE_TEST_TIMEOUT=60 bash ops/test-fx-factory-release.sh` — PASS.
  Fixture удалил реальный `build-orphaned`, сохранил обычную папку, symlink и
  его внешний target, а также подтвердил публикацию, rollback и signal-cleanup.
- Known baseline: общий `just check` в чистой копии дошёл до `staticcheck`, но
  среда прервала запуск после автоматической смены Go toolchain; целевой fixture
  и синтаксис прошли полностью.
- One next action: человеку проверить итог общего `just check` в CI и влить в main.

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

Проверен закреплённый diff от `main` `f2d9cce8f9038c566e3f2caf6df925d6d3c1bba2`
до кандидата `e2d99ab2fe2bba9230db17620ede204db2bb6e2f`: изменения ограничены
release-очисткой, fixture и документацией. `bash -n` и полный release fixture
с увеличенным лимитом 60 секунд завершились успешно; он удалил только реальный
`build-orphaned`, сохранил нерелизный каталог, symlink и внешний target, и
выполнил прежние publish/rollback/signal-сценарии. Чистый `just check` дошёл до
`staticcheck`, но был прерван средой после загрузки Go 1.25, поэтому общий итог
нужно подтвердить в CI до merge.
