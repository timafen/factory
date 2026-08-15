# CARD-0093 — Первое записанное поколение выпуска Factory

Implementation commit: 68f71c9566c20f9c1be406b2ced8c6760a9e7661 — откат вновь
публикует защищённые metadata, а битые указатели поколений останавливают выпуск
до build gates.

## HEAD

- Status: Implemented — повторно готово к Review.
- Branch: `factory/baf5d7a6-bd0-985f9f59-ec7`.
- Implementation commit: 68f71c9566c20f9c1be406b2ced8c6760a9e7661 — откат
  возвращает ownership/mode/sync metadata; preflight отклоняет два dangling-указателя.
- What changed: rollback восстанавливает owner, `0600` и fsync `release-info.json`;
  `current` и `previous` проверяются как существующие валидные поколения до сборки.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; повторный выпуск после
  rollback с `OWNER=factory:factory` и две dangling-ссылки покрыты регрессиями.
- Next action: повторно запустить Review.

## LOG

### 2026-08-12 — Specification

Найдена незаписанная исходная точка: `generations` пуст, а `current` и
`previous` отсутствуют. Спецификация вводит только программную защиту и
автотест; production не изменяется. Полный план:
`knowledge/specs/factory-first-recorded-release-generation.md`.

### 2026-08-12 — Implement

Добавлена явная граница первого выпуска: только пустая история и полностью
проверенный установленный комплект могут породить bootstrap. Bootstrap до
публикации проходит `verify_generation` и сохраняет полный SQLite-снимок.
`bash ops/test-fx-factory-release.sh` завершился PASS, включая три fail-closed
сценария и существующие crash/rollback-проверки.

### 2026-08-14 — Implement

После ребейза на свежий `main` защита первого поколения объединена с актуальной
защитой test gate. `bash ops/test-fx-factory-release.sh` завершился PASS:
bootstrap, metadata `0644`, отсутствие `release_id` и частичная история покрыты.

### 2026-08-15 — Implement

Исправлены замечания Review: при rollback metadata возвращается с ожидаемым
owner, mode `0600` и синхронизацией каталога, а обе dangling-ссылки на
поколения прерывают preflight до build gates. `bash ops/test-fx-factory-release.sh`
завершился PASS, включая повторный выпуск с `OWNER=factory:factory`.

## Следующее действие

Повторно запустить Review. До отдельного решения владельца не запускать
`fx factory release` в production.
