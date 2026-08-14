# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: b4bc7fb8896bb4341ae7d2fd5d669281bc2dc2f1 — реализован поздний перезапуск обновлённого release broker

## HEAD

- Status: Implemented and verified
- Branch: `factory/efd4579f-7bd-8d7c07fe-4d6`
- Implementation commit: `b4bc7fb8896bb4341ae7d2fd5d669281bc2dc2f1`
- What changed: после durable terminal commit посредник определяет замену своего inode и один раз перезапускает фиксированный systemd unit; release driver родительский процесс не останавливает.
- Evidence: `go test ./internal/releasebroker -run 'TestBroker.*Restart'` → PASS; `bash ops/test-fx-factory-release.sh` → PASS; смежные Go и installer-проверки → PASS.
- One next action: влить ветку в `main` после проверки поставки.

## LOG

### 2026-08-13 — Implement

Добавлен restart после committed marker и освобождения active operation для успешного и откатившегося выпуска, который заменил broker. Неизменённый или неопределимый executable, ошибка persistence и повторный POST restart не вызывают. Целевые Go-тесты, race-проверка, release fixture, installer-тест и синтаксическая проверка прошли.
