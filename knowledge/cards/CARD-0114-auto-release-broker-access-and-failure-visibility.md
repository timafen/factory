Implementation commit: fb94f15f989519f9a57080fe34029764c1fdced5 — восстановлены безопасный запуск автопоезда, видимость отказа и доказательная сверка 28 ожиданий.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: BLOCKED — полный Verify выявил красные проверки в изменённой области.
- Branch: `factory/e7506b0e-2a9-223ee49d-813`.
- Implementation commit: `fb94f15f989519f9a57080fe34029764c1fdced5`.
- Evidence: broker, failure/dedup, release и сверка 28 waits проходят целевые
  проверки; полный UI-набор, embedded UI gate и installer fixture не проходят.
- Blocker: `web/dist` не обновлён после изменения Overview; два Overview-теста
  получают закэшированный пустой dashboard, а fake `systemctl` ломает первую
  установку при обязательном перезапуске Pilot.
- Risk: production-манифест по-прежнему намеренно заблокирован до получения
  подтверждённого read-only snapshot и доказательств ручного выпуска.
- Next action: исправить изоляцию Overview/installer tests, пересобрать и
  закоммитить `web/dist`, затем повторить полный Verify.

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

### 2026-08-13 — Verify

Закреплены remote `main` `9af274d80462f6b10c4a95392a65e5022795a2e7`
и кандидат `939c8597214805d09ec8cce4d3b7e3070003b946` в отдельном bare repository.

| Критерий | Команда / проверка | Наблюдение |
|---|---|---|
| Broker запускает фиксированный Factory driver без `sudo` | `go test ./internal/releasebroker` | PASS; пакет завершён успешно, argv закреплён на `/usr/local/lib/fx-factory-release`. |
| Pilot имеет доступ к socket после установки | `./ops/test-install-project-release-broker.sh` | FAIL; fake `systemctl` требует version 2 при первом `restart factory-pilot.service`, fixture завершается 1. |
| Отказ фиксируется один раз, не завершает waits и виден владельцу | три целевых `python3 -m unittest ...` и один целевой `vitest` | PASS: 3 Python-сценария и новый Overview-сценарий; но полный `just ui-check` FAIL: 2 из 173 тестов из-за общего dashboard cache. |
| Сверка принимает ровно 28 waits и не меняет input/live state | `python3 ops/test-reconcile-factory-delivery-waits.py` | PASS; 6 тестов, включая fail-closed и exact-28. |
| Release и соседние rollback-пути сохранены | `./ops/test-fx-factory-release.sh`; `just test-release` | PASS; полный release fixture и воспроизводимые артефакты. |
| Полный Linux CI и embedded UI | команды Linux job из `.github/workflows/ci.yml`; `just test-browser` | BLOCKED: `web/dist` расходится после `just ui-build 0`; browser gate останавливается до Playwright. |

Общий прогон также выявил существующие отказы вне поставки: `staticcheck` в
`internal/worker/attempt_lifecycle_test.go` и два worker integration timeout.
Полный Pilot-набор: 250 пройдено, 2 отказа в correction provenance; относящиеся
к этой поставке failure/dedup сценарии проходят отдельно.
