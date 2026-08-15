Implementation commit: acddd76eb3bf1198ac0335fe54d852a4d64f2f1d — свободный совместимый исполнитель атомарно забирает ожидающую работу, а read-only Review повторяется через `NOT READY`.

# CARD-0169 — Очередь не простаивает при свободном совместимом исполнителе

## HEAD

- Status: Specified.
- Branch: `factory/87d135a7-02d-e923fdb2-c1f`.
- Scope: проверяемый контракт claim, read-only Review и 24-часовой метрики;
  продуктовый код этим этапом не изменяется.
- Next action: Review спецификации и целевых регрессий перед любым изменением
  поведения.

## Контекст

Исходное назначение не должно резервировать queued работу навсегда. Claim берёт
старейшую совместимую работу для свободного worker, а не только работу, изначально
назначенную ему. Совместимость означает одинаковый runtime, advertised repository
и доступные общую и retained capacity.

## Доказательства контракта

- атомарность и единственный claim: `TestCompatibleWorkersClaimOnceWhileWriterContinues`;
- перенос свободному совместимому worker: `TestCompatibleIdleWorkerClaimsQueuedAssignment`;
- отсутствие переноса несовместимому worker и повторная проверка:
  `TestQueuedAssignmentRejectsIncompatibleWorkers`;
- неизменяемый read-only snapshot и правило committed snapshot:
  `TestReadOnlyWorkflowMetadataIsSnapshottedIntoClaims` и
  `TestReadOnlyClaimCarriesCommittedSnapshotRule`;
- `NOT READY` возвращает тот же Review в очередь без второго активного attempt:
  `TestReadOnlyNotReadyIsRequeuedWithoutDuplicateAttempt`.

## Ограничения

Не менять длительность lease, лимиты capacity, retry policy завершённых задач,
изоляцию worktree или первоначальный выбор worker при создании Task. Метрика
переназначений считается по журналу событий, не по количеству последующих
обновлений execution.
