# CARD-0097 — Осиротевшие папки release-сборок освобождают место безопасно

Implementation commit: bb93d7c8df3ff50f4ffb8b5f86575bd89a36f18b — signal-fixture запускает обязательный UI/Go gate до позднего HUP.

## HEAD

- Status: BLOCKED: signal-HUP исправлен, но полный fixture остановился на независимом rollback владельца; до PASS слияние запрещено.
- Branch: `factory/52d60353-42d-a48a3a2f-87b`.
- Specification: `knowledge/specs/cleanup-orphaned-release-builds.md`.
- What changed: асинхронный signal-fixture теперь передаёт `FACTORY_RELEASE_DEEP_GATE=1`,
  поэтому UI и Go gate действительно запущены и синхронизированы до HUP.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` — PASS;
  полный fixture с лимитом 120 секунд прошёл все HUP/TERM сценарии и позже остановился
  на rollback владельца: отсутствует fresh healthy-регистрация `worker-release-test`.
- One next action: повторить полный fixture в свободной среде и устранить rollback владельца, если сбой повторится.

## LOG

### 2026-08-15 — Implement

Найдена гонка в самом signal-fixture: его фоновый launcher не передавал
`FACTORY_RELEASE_DEEP_GATE=1`, поэтому быстрый путь обходил UI/Go gate и
ожидание `ui-running` закономерно истекало. Режим передан без увеличения
таймаутов; полный fixture прошёл HUP/TERM-сценарии, но позднее остановился на
отдельной проверке rollback владельца без healthy-регистрации воркера.

### 2026-08-15 — Implement

По решению владельца целевой fixture повторён в свободной от другого release
fixture среде с лимитом 120 секунд на выпуск и внешней диагностикой в 12 минут.
Повтор снова дошёл до позднего `signal-HUP-1`, но не дождался `ui-running`;
внешний лимит не был исчерпан. Изменение возвращено на доработку без слияния;
диагностический вывод сохранён в `/tmp/card-0097-release-fixture-retry.log`.

### 2026-08-15 — Implement

Реализация перенесена на свежий `main`; конфликт в release-скриптах разрешён
с сохранением актуальной подготовки release-каталогов до безопасной очистки.
`bash -n` и полный `FACTORY_RELEASE_TEST_TIMEOUT=120 bash
ops/test-fx-factory-release.sh` прошли: fixture удалил только реальный
`build-orphaned`, сохранил обычную папку, symlink и внешний target, а также
подтвердил publish, rollback и signal-cleanup.

### 2026-08-14 — Implement

Реализация повторно сверена со всеми критериями спецификации. `bash -n`
и `FACTORY_RELEASE_TEST_TIMEOUT=60 bash ops/test-fx-factory-release.sh` прошли:
штатный выпуск удалил реальный `build-orphaned`, сохранил чужую папку,
symlink и его внешний target, а также все publish/rollback/signal-сценарии.
Общий `just check` остановился на прежнем SA4000 вне области задачи.

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
