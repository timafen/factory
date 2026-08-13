# CARD-0108 — Одноразово развести исторические дубли номеров карточек

## HEAD

Status: Implemented — исторические дубли разведены.
Branch: factory/b9d8f675-869-422a8d74-2a6
Implementation commit: 1a02b134c2c9bde216df46201b3a17b19a436a9a — утилита, тесты и одноразовое разведение карточек на свежем `main`.
What changed: добавлены dry-run/`--apply`, детерминированное переименование 41 неканонической карточки и обновление точных ссылок.
Evidence: миграционные тесты — OK (4); резервирование Пилота — OK (5); повторный dry-run и проверка дублей — чистые.
Next action: проверить свежую ветку на Verify и влить изменение в `main`.

## LOG

### 2026-08-12 — Implement

После перебазирования на свежий `origin/main` карточка закреплена за
реальным коммитом реализации `345aface075ed562ee970b21544b4672869228d9` в
текущей ветке. Целевые тесты утилиты и проверка отсутствия дублей
повторены на этом снимке.

### 2026-08-12 — Specification

В каталоге `knowledge/cards/` остались 23 повторяющихся номера. Specification
зафиксировала детерминированный выбор лексикографически первого пути, свободные
номера после максимума, замену только полных ссылок и отсутствие изменений в
Пилоте.

### 2026-08-12 — Implement

Применён dry-run со свежим каталогом: 105 файлов, 23 группы дублей, 38
переименований. Канонический лексикографически первый путь оставлен, остальные
получили номера 0109–0146; содержимое карточек сохранено, обновлены только
точные ссылки на старые пути.

Манифест old-path → new-path:

```text
CARD-0034-internal-factory-pipeline-patrol.md -> CARD-0109-internal-factory-pipeline-patrol.md
CARD-0034-pilot-brain-provider-fallback.md -> CARD-0110-pilot-brain-provider-fallback.md
CARD-0034-plan-priority-autostart.md -> CARD-0111-plan-priority-autostart.md
CARD-0036-ui-shared-eslint-errors.md -> CARD-0112-ui-shared-eslint-errors.md
CARD-0037-server-load-admission.md -> CARD-0113-server-load-admission.md
CARD-0038-pilot-config-server-schema-sync.md -> CARD-0114-pilot-config-server-schema-sync.md
CARD-0038-sandbox-ebay-owner-consent.md -> CARD-0115-sandbox-ebay-owner-consent.md
CARD-0039-stage-specific-agent-rules.md -> CARD-0116-stage-specific-agent-rules.md
CARD-0041-readable-work-history.md -> CARD-0117-readable-work-history.md
CARD-0041-stalled-work-diagnosis-repair.md -> CARD-0118-stalled-work-diagnosis-repair.md
CARD-0043-overview-project-products.md -> CARD-0119-overview-project-products.md
CARD-0045-fable-automation-migration-audit.md -> CARD-0120-fable-automation-migration-audit.md
CARD-0045-factory-claude-patrol-automation.md -> CARD-0121-factory-claude-patrol-automation.md
CARD-0047-diag-repair-duplicate-active-runs.md -> CARD-0122-diag-repair-duplicate-active-runs.md
CARD-0047-factory-control-bootstrap.md -> CARD-0123-factory-control-bootstrap.md
CARD-0047-idempotent-verify-merge.md -> CARD-0124-idempotent-verify-merge.md
CARD-0047-worker-utf8-runtime.md -> CARD-0125-worker-utf8-runtime.md
CARD-0048-offline-claude-haiku-retained-worktree.md -> CARD-0126-offline-claude-haiku-retained-worktree.md
CARD-0048-orphaned-paused-pipeline-cleanup.md -> CARD-0127-orphaned-paused-pipeline-cleanup.md
CARD-0048-server-browser-network-isolation.md -> CARD-0128-server-browser-network-isolation.md
CARD-0051-pilot-local-worker-notification-channel.md -> CARD-0129-pilot-local-worker-notification-channel.md
CARD-0051-server-browser-network-isolation-verification.md -> CARD-0130-server-browser-network-isolation-verification.md
CARD-0052-pilot-explicit-wait-action.md -> CARD-0131-pilot-explicit-wait-action.md
CARD-0052-pipeline-watch-cycle.md -> CARD-0132-pipeline-watch-cycle.md
CARD-0052-test-helper-cleanup.md -> CARD-0133-test-helper-cleanup.md
CARD-0055-worker-slowest-tests.md -> CARD-0134-worker-slowest-tests.md
CARD-0057-review-return-reasons.md -> CARD-0135-review-return-reasons.md
CARD-0058-single-work-heavy-stage-deduplication.md -> CARD-0136-single-work-heavy-stage-deduplication.md
CARD-0059-recent-done-final-results.md -> CARD-0137-recent-done-final-results.md
CARD-0060-work-completed-task-visible.md -> CARD-0138-work-completed-task-visible.md
CARD-0067-janitor-confirmation-route-regression.md -> CARD-0139-janitor-confirmation-route-regression.md
CARD-0067-release-all-worker-services.md -> CARD-0140-release-all-worker-services.md
CARD-0068-janitor-clears-already-missing-retained-worktree.md -> CARD-0141-janitor-clears-already-missing-retained-worktree.md
CARD-0068-settings-conflict-safe-reload.md -> CARD-0142-settings-conflict-safe-reload.md
CARD-0068-stable-work-done-browser-check.md -> CARD-0143-stable-work-done-browser-check.md
CARD-0069-specification-branch-handoff.md -> CARD-0144-specification-branch-handoff.md
CARD-0083-settings-save-without-first-verify.md -> CARD-0145-settings-save-without-first-verify.md
CARD-0089-release-process-recovery-review-fixes.md -> CARD-0146-release-process-recovery-review-fixes.md
```

Проверено целевыми unittest, `git diff --check`, отсутствием дублей по
числовому префиксу и повторным dry-run (`No duplicate card numbers found.`).
Изменён только каталог знаний, ссылки в спецификациях и новая утилита с её
тестом; `pilot/pilot.py` и `pilot/test_pilot.py` не менялись.

### 2026-08-12 — Implement

На текущей ветке обнаружен оставшийся bare-файл `CARD-0030.md`, который
конфликтовал с общим backlog по числовому префиксу. Файл переименован в
`CARD-0148.md` без изменения содержимого; проверка дублей по всем `CARD-*.md`
теперь не находит совпадений.

### 2026-08-12 — Implement

В текущей ветке `HEAD` карточки закреплён за реальным кодовым коммитом
`c7edbbf965c3e480ef053c044cc15ad4508d5f55`; повторены 4 теста утилиты,
5 тестов резервирования номера, проверка уникальности и чистый dry-run.

### 2026-08-13 — Implement

На свежем `origin/main` добавлены утилита и её тесты, затем один раз применён
детерминированный план: 41 неканоническая карточка получила свободный номер,
а точные ссылки обновлены. Проверены 4 теста утилиты, 5 тестов резервирования
Пилота, отсутствие дублей и пустой повторный dry-run.
