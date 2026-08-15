# CARD-0132 — Корректировка выпуска переживает перезапуск Pilot

Implementation commit: 4dfd93f66ea9b197f879a2b9d62d09c997820f41 — Pilot сохраняет provenance корректировки и продолжает `review_return` и `verify_return` после перезапуска.

## HEAD

- Status: Implemented — ready for Verify.
- Branch: `factory/f5ca2c64-86a-372f4e0f-c36`.
- Implementation commit: 4dfd93f66ea9b197f879a2b9d62d09c997820f41 — сохранены происхождение и idempotent-событие корректировки, чтобы новый процесс продолжал ту же работу.
- What changed: реальный перезапуск Pilot продолжает `review_return` и
  `verify_return` через Review, Verify и финализацию без дубликата конвейера.
- Evidence: `python3 -m unittest -v pilot.test_pilot` — PASS: 306 tests,
  13 skipped, включая оба сценария восстановления.
- Next action: собрать новый кандидат от свежего `main` и повторить Verify; прежний кандидат не выпускать.

## LOG

### 2026-08-14 — Implement

После получения ответа владельца проверено восстановление двух возвратов после
реального перезапуска процесса. Фактический коммит реализации сохраняет
устойчивое происхождение корректировки и не создаёт второй конвейер.
`python3 -m unittest -v pilot.test_pilot` — PASS: 306 tests, 13 skipped.
