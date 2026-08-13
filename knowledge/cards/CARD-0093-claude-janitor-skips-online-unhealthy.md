# CARD-0093 — санитар пропускает online/unhealthy Claude

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/d7f5f772-3e8-36f57e0c-bd0`
- Implementation commit: 8f0335b1d6d13ba6d8340944258837841127fee4 — тест доказывает, что санитар пропускает online/unhealthy Claude с retained worktree.
- What changed: fixture online/unhealthy worker теперь содержит retained worktree, поэтому тест ловит ошибочный restart; offline cleanup и healthy worker сценарии сохранены.
- Evidence: целевой `bash ops/test-factory-janitor.sh` → 4 PASS; сборка, Go, race, UI, release, launcher и tooling → PASS. Общий `staticcheck` падает на прежнем `internal/worker/attempt_lifecycle_test.go:31`, browser sandbox заблокирован политикой контейнера; оба файла вне diff.
- One next action: human merge после просмотра доказательств Verify.

## LOG

### 2026-08-12 — Implement

Online/unhealthy Claude больше не останавливается и не запускается санитаром, а offline idle retained worker продолжает проходить карантин и точечное подтверждение. Регрессия проверяет stop/start, state-файл, карантин, ошибку API и сохранность неперемещённого результата.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Online/unhealthy Claude не перезапускается | `bash ops/test-factory-janitor.sh` | Нет `stop/start`, worktree остаётся на месте, worker отсутствует в state-файле. |
| Offline idle Claude с retained worktree очищается безопасно | Тот же тест | Карантин, API-подтверждение, обработка ошибки API и неперемещённый результат сохранены. |
| Поставка не ломает проект | Полный набор `just`-проверок | Backend, UI и 21 браузерный тест прошли. |

### 2026-08-13 — Implement

Усилен тест online/unhealthy worker: API возвращает retained worktree, поэтому
проверка действительно защищает от холостого restart, карантина и резервирования.
Исправление находится в отдельном коммите реализации `8f0335b1d6d13ba6d8340944258837841127fee4`.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Online/unhealthy worker с retained worktree не перезапускается | `bash ops/test-factory-janitor.sh` | Нет `stop/start`, quarantine и state-записи; worktree остаётся на месте. |
| Offline idle worker по-прежнему очищается безопасно | Тот же тест | Перемещённые результаты подтверждаются через API, неперемещённый остаётся; ошибка API журналируется. |
| Online/healthy retained worktree не затрагивается | Тот же тест | Worktree остаётся на месте и не попадает в quarantine. |
| Поставка собирается и не ломает смежное поведение | `just build`; Go, race, UI, release, launcher и tooling recipes | PASS; целевой тест сообщает 4 PASS. |
| Полный набор проверен с учётом долгов окружения | `just check`; `just test-browser` | `staticcheck` на прежнем файле вне diff; browser sandbox запрещён `no new privileges`. |
| Граница задачи не дублирует исправление health-probe | Сопоставление CARD-0093 и CARD-0098 | Здесь защита санитаря; первопричина ложного `unhealthy` остаётся отдельной задачей CARD-0098. |
