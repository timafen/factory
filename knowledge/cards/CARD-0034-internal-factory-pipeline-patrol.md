# CARD-0034 — Встроенный патруль конвейера Фабрики

## HEAD

- Status: Implement + Test complete — обязательная UI-проверка зелёная.
- Branch: `factory/fda81935-551-a358c458-2b4`.
- Head commit: `7520deb` (реализация и проверки поверх `origin/main` `f18970a`).
- Specification: `knowledge/specs/internal-factory-pipeline-patrol.md`.
- What changed: браузерный контракт синхронизирован с текущими экранами и API; узкий Automation-экран больше не растягивает длинный runbook.
- Evidence: Playwright → 18 passed; отдельный app `tsc` → exit 0; web unit → 101 passed; pilot → 32 OK; Go → OK; build/lint → OK.
- One next action: Review сверяет поставку и передаёт её в Verify.

## LOG

### 2026-08-08 — Specification

Зафиксирован минимальный путь: существующий pilot патрулирует переходы сам, ждёт безопасное окно, не дублирует живую работу и после двух толчков сообщает владельцу об остановке. Внешний LLM-помощник, отдельный процесс и новый планировщик не участвуют. Спецификация содержит проверяемые обещания по двум файлам реализации и целевой команде теста.

### 2026-08-08 — Implement

Патруль получил явно закреплённый контракт живых состояний и шесть изолированных сценариев: безопасное ожидание, одиночное продолжение с тем же репозиторием, подавление дубля, пауза владельца, завершённый конвейер и однократная эскалация после двух толчков. Автономность проверена запретом вызова внешнего оркестратора. Целевые и полные тесты pilot, Go-регрессия и web-сборка прошли.

### 2026-08-08 — Scope correction

Из поставки исключены `pilot/pilot.py` и `pilot/test_pilot.py`: задача этой ветки ограничена карточкой и спецификацией, поэтому реализация патруля должна прийти отдельной поставкой. Проверка трёхточечного диффа относительно `origin/main` подтверждает ровно два заявленных файла; проверка пробелов проходит.

### 2026-08-08 — Implement

Отдельная поставка вернула только обещанную реализацию `pilot`: живые состояния закреплены как контракт, а шесть тестов доказывают автономное и идемпотентное возобновление. Целевой и полный pilot-наборы, а также web-сборка прошли. Полная Go-регрессия зафиксировала базовую ошибку маршрута каталога репозиториев вне области этой карточки.

### 2026-08-08 — Implement

На чистом снимке свежего `origin/main` отдельно воспроизведён базовый 404 в `TestHTTPManagedRepositoryCatalog`; отсутствующий маршрут каталога исполнителя восстановлен минимальным коммитом. После перебазирования патруля предметные и полные проверки Python и Go, а также web-сборка прошли, поэтому прежняя блокировка снята.

### 2026-08-08 — Verify

| Критерий | Проверка | Наблюдаемый результат |
| --- | --- | --- |
| Потерянный переход ждёт 600 секунд и создаётся один раз | `python3 -m unittest pilot.test_pilot.PipelineWatchTests` | сценарии ожидания и одиночного запуска прошли; этап получает исходный репозиторий, revision и worker |
| Живая задача не получает дубль | та же команда | сценарий сброса памяти остановки живой задачей прошёл |
| Пауза владельца сохраняется | та же команда | сценарий `stopped_owner` прошёл без создания задачи |
| После двух попыток есть одна эскалация | та же команда | сценарий лимита толчков прошёл: новых задач нет, уведомление одно |
| Патруль автономен | та же команда | заглушка внешнего оркестратора не вызвана; все 6 сценариев прошли без сети и второго процесса |

Регрессии: `python3 -m unittest pilot.test_pilot` — 7 OK; `go test -timeout 5m ./...` — OK; `go test ./internal/controlplane/... -run '^TestHTTPManagedRepositoryCatalog$' -count=1` — OK; после `npm ci --prefix web` команда `npm --prefix web run build` — OK. Дифф от `origin/main...HEAD` содержит пять заявленных файлов, `git diff --check` чист.

### 2026-08-09 — Implement

На свежем `origin/main` повторно проверено, что обещанные `pilot/pilot.py` и `pilot/test_pilot.py` уже содержат автономный сторож и шесть предметных сценариев; дублировать реализацию в этой ветке не потребовалось. `python3 -m unittest pilot.test_pilot.PipelineWatchTests` — 6 OK, `python3 -m unittest pilot.test_pilot` — 32 OK, `go test -timeout 5m ./...` — OK, после `npm ci --prefix web` команда `npm --prefix web run build` — OK. Открытым остаётся заявленный в спецификации риск: несколько одновременно запущенных процессов pilot не координируются распределённой арендой.

### 2026-08-09 — Implement

По ответу владельца на снимке `origin/main` `fe7704b` выполнена отдельная обязательная проверка интерфейса. Первый прогон обнаружил устаревшие ожидания Playwright, старый формат `stages` в e2e-fixture, устаревший mock списка моделей и горизонтальный выход Automation detail на 390 px; контракт и узкая раскладка исправлены. Полный успешный результат `npm run test:browser`:

```text
✓  1 shows the Factory status and active work on the overview (1.2s)
✓  2 creates, pins, revises, and disables a reusable Workflow (3.1s)
✓  3 runs the complete UI to real-worker and Git-worktree workflow (4.6s)
✓  4 cancels active work running in the real worker (16.9s)
✓  5 renders every state and saves the desktop Work view (1.4s)
✓  6 confirms and deletes terminal task history (1.9s)
✓  7 shows worker capacity, current work, retained cleanup, and saves Workers (2.6s)
✓  8 delegates with worker-specific repositories and preserves the task on refresh (1.8s)
✓  9 confirms queued cancellation and explicitly retries a failure (1.3s)
✓ 10 shows ordered progress and long task detail (3.2s)
✓ 11 supports narrow grouped layouts and saves narrow screenshots (3.3s)
✓ 12 opens and closes delegation from the keyboard (1.2s)
✓ 13 manages repository routing end to end and preserves add input while polling (13.2s)
✓ 14 previews and dispatches one typed GitHub issue Automation without duplication (9.6s)
✓ 15 previews and dispatches one typed GitHub pull-request Automation without duplication (10.7s)
✓ 16 previews, enables, and runs a schedule Automation through the ordinary task path (4.2s)
✓ 17 migrates a locked legacy snapshot through Resume and Finalize (3.2s)
✓ 18 edits pilot settings from the Settings screen (1.4s)
18 passed (2.0m)
```

Дополнительные ворота: `npx tsc -p tsconfig.app.json --noEmit --pretty false` — exit 0; `npm test -- --reporter=dot` — 101 passed; `npm run lint` — exit 0; `npm run build` — exit 0; `python3 -m unittest pilot.test_pilot.PipelineWatchTests` — 6 OK; `python3 -m unittest pilot.test_pilot` — 32 OK; `go test -timeout 5m ./...` — OK. После финального rebase на новый свежий `origin/main` `f18970a` отдельно повторены Playwright — 18 passed (2.1m), app `tsc` — exit 0 и сторож — 6 OK. Открытый риск прежний: одновременно запущенные процессы pilot не координируются распределённой арендой.
