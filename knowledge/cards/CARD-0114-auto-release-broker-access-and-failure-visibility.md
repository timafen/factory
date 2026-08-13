Implementation commit: 172b6503e10e687c979ffe150d04c3abe1a35a51 — встроенная панель выпуска пересобрана вместе с безопасным broker, доступом Pilot и видимостью отказа.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: PASS.
- Branch: `factory/ef17f71f-1d2-9d4b125e-236`.
- Implementation commit: `172b6503e10e687c979ffe150d04c3abe1a35a51`.
- What changed: broker запускает Factory driver без `sudo`; Pilot получает группу
  socket; отказ выпуска сохраняется один раз и показывается владельцу.
- What changed: installer fixture подтверждает первый restart Pilot, а `web/dist`
  содержит актуальный Overview для embedded browser gate.
- Evidence: `go test ./internal/releasebroker`, installer fixture, сверка 28 waits,
  `just ui-check`, `just test-browser` и `just test-release` — PASS.
- Risk: production-манифест намеренно остаётся заблокированным до подтверждённого
  read-only snapshot и доказательств ручного выпуска.
- Next action: Verify/Review может принять поставку по полному набору доказательств.

## LOG

### 2026-08-13 — Implement

Broker запускает фиксированный Factory driver напрямую без `sudo`, а Pilot получает
доступ к socket через supplementary group. Durable-отказ записывается один раз,
не завершает waits и отображается без внутренних идентификаторов. Reconciliation
проверяет ровно 28 waits, не меняя live state. Обновлённый `web/dist` проходит
embedded browser gate; installer fixture подтверждает безопасный первый restart.
