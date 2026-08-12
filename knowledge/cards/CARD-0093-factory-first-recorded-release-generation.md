# CARD-0093 — Первое записанное поколение выпуска Factory

Implementation commit: 5746dbc1fa1314497dc1fe69c68f0162e236a866 — реализован
базовый механизм проверяемых поколений, полного снимка и rollback-комплекта,
на который опирается эта защита первого выпуска.

## HEAD

- Status: Specified — ожидает реализации.
- What is requested: явный fail-closed bootstrap первого recorded release и
  автоматическое доказательство его корректности.
- Owner decision: не менять `factory-current.json`, не выполнять живой выпуск
  и не создавать поколения вручную, пока не проверена восстановимая исходная
  точка.
- Implementation scope: `ops/fx-factory-release`,
  `ops/test-fx-factory-release.sh`.
- Required evidence: `bash ops/test-fx-factory-release.sh` завершается с кодом
  0 и проверяет создание `previous` из валидной пустой истории, а также
  безопасные отказы для metadata `0644`, отсутствующего `release_id` и
  частичной истории.

## LOG

### 2026-08-12 — Specification

Найдена незаписанная исходная точка: `generations` пуст, а `current` и
`previous` отсутствуют. Спецификация вводит только программную защиту и
автотест; production не изменяется. Полный план:
`knowledge/specs/factory-first-recorded-release-generation.md`.

## Следующее действие

Передать карточку в Implement. До успешной реализации и отдельного решения
владельца не исправлять права metadata и не запускать `fx factory release`.
