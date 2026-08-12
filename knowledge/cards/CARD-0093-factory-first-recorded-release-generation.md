# CARD-0093 — Первое записанное поколение выпуска Factory

Implementation commit: d3873a8262288e8249e9e3dcc3ebfea86ef06326 — первый выпуск
проверяет исходную точку, записывает полный bootstrap-комплект и отказывается
от небезопасной истории до сборки или остановки служб.

## HEAD

- Status: Implemented — готово к Review.
- Branch: `factory/19c563f0-6f3-3c4b0d3b-34b`.
- Implementation commit: d3873a8262288e8249e9e3dcc3ebfea86ef06326 — fail-closed
  bootstrap первого recorded release с полным проверяемым rollback-комплектом.
- What changed: preflight до сборки проверяет пустую/целую историю, metadata
  `0600`, `release_id`, SHA и живые rollback artifacts; bootstrap содержит
  исходные metadata, inventory, service state и SQLite-снимок.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; сценарии `0644`,
  отсутствующего `release_id` и частичной истории не запускают сборку или службы.
- Next action: передать в Review без живого выпуска и без ручной правки metadata.

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

## Следующее действие

Передать карточку в Review. До отдельного решения владельца не исправлять
права живой metadata и не запускать `fx factory release`.
