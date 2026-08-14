# CARD-0127: Повтор предполётной проверки deleted-inode

Implementation commit: 5746dbc1fa1314497dc1fe69c68f0162e236a866 — выпуск до мутаций проверяет executable активных unit, сохраняет бортовой журнал и прекращает release при deleted inode.

## Статус

Status: Specification ready. Владелец разрешил повторную предполётную проверку; предыдущий обрыв вывода не считается результатом release.

## Результат для владельца

Повторная проверка теперь определена как отдельная диагностируемая операция: deleted inode останавливает выпуск до изменения Factory, а новая потеря supervisor output требует сохранить последний шаг и полный voyage-log, а не назвать попытку успешной.

## Scope

- `knowledge/specs/factory-release-preflight-deleted-inode-retry.md`
- операционная проверка существующих `ops/fx-factory-release`, `ops/test-fx-factory-release.sh`, `ops/test-factory-release-systemd.sh` и `docs/factory-handover-sol.md`

## Приёмка

Обязательная проверка реализации: `bash ops/test-fx-factory-release.sh` завершается с кодом 0. Для живого повтора результатом является полный voyage-log с последним шагом и exit code; при `deleted-inode` перед повтором перезапускается только названный unit.

## Ограничения

Эта работа — только Specification: не меняет продуктовый код, UI, production, службы и базу. После повторного запуска при новом обрыве в карточку/диагностику переносится полный вывод ошибки и точный шаг.
