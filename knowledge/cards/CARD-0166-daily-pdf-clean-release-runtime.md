Implementation commit: ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5 — ранее реализованы ежедневный PDF, capture/renderer и browser installer; это фундамент, а не реализация данной спецификации.

# CARD-0166: ежедневный PDF после чистого штатного релиза

## HEAD

Status: Specified — awaiting Implement
Branch: `factory/b60e94a6-e1d-61b860d7-0e7`
What changed: определён воспроизводимый release-контракт постоянного browser runtime,
который не зависит от ручных Node-модулей в `/opt/factory`.
Evidence: текущие renderer/capture используют fallback через `process.cwd()/web`,
а `ops/fx-factory-release` удаляет временный checkout и не публикует browser payload.
One next action: реализовать постоянное поколение browser runtime и clean-host
регрессию из `knowledge/specs/daily-pdf-clean-release-runtime.md`.

## LOG

### 2026-08-14 — Specification

Подтверждена причина ручного восстановления: встроенному PDF renderer нужен
`playwright`, но штатный выпуск оставляет `npm ci` только во временном checkout.
Спецификация требует устанавливать и проверять browser runtime до остановки служб,
публиковать его атомарно вместе с выпуском и возвращать при rollback. Отдельный тест
должен получить `%PDF-` после удаления checkout на fixture без `/opt/factory`.
Продуктовый код и UI на этапе Specification не изменялись.
