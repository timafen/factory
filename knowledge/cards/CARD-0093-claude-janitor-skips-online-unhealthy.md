# CARD-0093 — санитар пропускает online/unhealthy Claude

## HEAD

- Status: Implemented
- Branch: `factory/5149d29e-032-4f8c9176-d33`
- Implementation commit: ca459e547e06bbd2ed9c57de1f61e10a4f3d2801 — санитар освобождает только offline idle Claude с retained worktrees.
- What changed: online/unhealthy workers удалены из выборки санитаря; тест проверяет отсутствие stop/start и резервирования попытки. Offline retained cleanup, карантин и API-подтверждение сохранены.
- Evidence: `bash ops/test-factory-janitor.sh` → 4 PASS; `bash -n` и `git diff --check` → PASS.
- One next action: после вливания наблюдать журнал санитаря на отсутствие повторных холостых перезапусков Claude.

## LOG

### 2026-08-12 — Implement

Online/unhealthy Claude больше не останавливается и не запускается санитаром, а offline idle retained worker продолжает проходить карантин и точечное подтверждение. Регрессия проверяет stop/start, state-файл, карантин, ошибку API и сохранность неперемещённого результата.
