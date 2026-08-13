Implementation commit: fb94f15f989519f9a57080fe34029764c1fdced5 — восстановлены безопасный запуск автопоезда, видимость отказа и доказательная сверка 28 ожиданий.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: Implement + Test — готово к Verify.
- Branch: `factory/e7506b0e-2a9-223ee49d-813`.
- Implementation commit: `fb94f15f989519f9a57080fe34029764c1fdced5`.
- What changed: Pilot получает группу broker-сокета, а привилегированный broker
  запускает фиксированный Factory driver напрямую, без `sudo` и shell.
- What changed: terminal failure создаёт один durable event и виден в Overview;
  one-shot tool выпускает только отдельный state после полной сверки 28 waits.
- Evidence: installer fixture, release fixture, Go broker tests, 16 Pilot tests,
  6 reconciliation tests и 29 Overview tests завершились успешно; web build успешен.
- Risk: production-манифест намеренно заблокирован до получения подтверждённого
  read-only snapshot и доказательств успешного ручного выпуска.
- Next action: Verify один раз запускает полный проектный набор и проверяет diff
  от свежего remote default branch.

## LOG

### 2026-08-13 — Implement

Drop-in supplementary group перенесён на `factory-pilot.service`; installer
сначала атомарно устанавливает новый override и broker, затем перезапускает
Pilot. Factory release/rollback направлены на фиксированный
`/usr/local/lib/fx-factory-release`, остальные adapters сохранили прежний `fx`.

Pilot durable-сохраняет один `<generation>:failed`, журналирует его append-once
и показывает текущий либо последний неуспешный состав без SHA, PID и внутренних
идентификаторов. Failure не создаёт receipts и не завершает waits.

Reconciliation проверяет checksum preimage, совпадение release evidence,
отсутствие transaction journal, точное множество 28 waits, merge intents и Git
ancestry. Он создаёт отдельные output/audit файлы и никогда не меняет input/live
state; fixture подтвердил fail-closed случаи и восстановление ровно 28 waits.
