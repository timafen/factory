# CARD-0093 — санитар пропускает online/unhealthy Claude

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/5149d29e-032-4f8c9176-d33`
- Implementation commit: ca459e547e06bbd2ed9c57de1f61e10a4f3d2801 — санитар освобождает только offline idle Claude с retained worktrees.
- What changed: online/unhealthy workers удалены из выборки санитаря; тест проверяет отсутствие stop/start и резервирования попытки. Offline retained cleanup, карантин и API-подтверждение сохранены.
- Evidence: полный набор `just format-check`, `just vet`, `just vuln`, `just boundary`, `just test`, `just test-worker-race`, `just test-tooling`, `just test-launcher`, `just ui-check`, `just test-browser` → PASS; целевой `bash ops/test-factory-janitor.sh` → 4 PASS; `bash -n` и `git diff --check` → PASS.
- One next action: human merge после просмотра этой проверки.

## LOG

### 2026-08-12 — Implement

Online/unhealthy Claude больше не останавливается и не запускается санитаром, а offline idle retained worker продолжает проходить карантин и точечное подтверждение. Регрессия проверяет stop/start, state-файл, карантин, ошибку API и сохранность неперемещённого результата.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Online/unhealthy Claude не перезапускается | `bash ops/test-factory-janitor.sh` | Нет `stop/start`, worktree остаётся на месте, worker отсутствует в state-файле. |
| Offline idle Claude с retained worktree очищается безопасно | Тот же тест | Карантин, API-подтверждение, обработка ошибки API и неперемещённый результат сохранены. |
| Поставка не ломает проект | Полный набор `just`-проверок | Backend, UI и 21 браузерный тест прошли. |
