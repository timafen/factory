# CARD-0093 — санитар пропускает online/unhealthy Claude

## HEAD

- Status: Implemented — awaiting verification and human merge
- Branch: `factory/d7f5f772-3e8-36f57e0c-bd0`
- Implementation commit: 8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad — тест доказывает, что санитар пропускает online/unhealthy Claude с retained worktree.
- What changed: fixture online/unhealthy worker теперь содержит retained worktree, поэтому тест ловит ошибочный restart; offline cleanup и healthy worker сценарии сохранены.
- Evidence: целевой `bash ops/test-factory-janitor.sh` → 4 PASS; `bash -n ops/test-factory-janitor.sh` и `git diff --check` → PASS.
- One next action: выполнить полный набор проверок после rebase и передать ветку на human merge.

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
Исправление находится в отдельном коммите реализации `8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad`.
