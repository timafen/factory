Implementation commit: f18d6440e3c62637143eb0560bfd1d1e03e72c92 — broker работает без sudo, Pilot получает доступ к socket и показывает сохранённый отказ выпуска.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: PASS.
- Branch: `factory/c5dc0866-f0c-a2b61a4a-38e`.
- Implementation commit: `f18d6440e3c62637143eb0560bfd1d1e03e72c92` — broker
  работает без `sudo`, Pilot получает группу socket и показывает сохранённый отказ.
- What changed: broker запускает Factory driver без `sudo`; Pilot получает группу
  socket; отказ выпуска сохраняется один раз и показывается владельцу.
- What changed: installer fixture подтверждает первый restart Pilot; отдельный коммит
  `172b6503e10e687c979ffe150d04c3abe1a35a51` содержит только сборку `web/dist`.
- Evidence: `go test ./internal/releasebroker`, installer fixture, сверка 28 waits,
  `just ui-check`, `just test-browser` и `just test-release` — PASS.
- Risk: production-манифест намеренно остаётся заблокированным до подтверждённого
  read-only snapshot и доказательств ручного выпуска.
- Next action: повторно пройти Review с исправленным доказательством реализации.

## LOG

### 2026-08-13 — Implement

Broker запускает фиксированный Factory driver напрямую без `sudo`, а Pilot получает
доступ к socket через supplementary group. Durable-отказ записывается один раз,
не завершает waits и отображается без внутренних идентификаторов. Reconciliation
проверяет ровно 28 waits, не меняя live state. Обновлённый `web/dist` проходит
embedded browser gate; installer fixture подтверждает безопасный первый restart.

### 2026-08-13 — Implement

Исправлена атрибуция поставки: реализация broker и Pilot находится в коммите
`f18d6440e3c62637143eb0560bfd1d1e03e72c92`, а коммит
`172b6503e10e687c979ffe150d04c3abe1a35a51` только пересобирает встроенный
интерфейс. Fixture установки теперь корректно различает перезапуски broker и
Pilot. Production-манифест остаётся заблокированным до ручного выпуска.
