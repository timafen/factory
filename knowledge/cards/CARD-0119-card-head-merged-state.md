# HEAD карточки отражает включённую проверку Gate

Implementation commit: f2d9cce8f9038c566e3f2caf6df925d6d3c1bba2 — проверка не теряет ошибку Gate за форкающим launcher.

## HEAD

Status: Implemented — CARD-0083 синхронизирована с фактическим `main`.
Branch: factory/a23b34a6-244-57387320-d56.
Implementation commit: f2d9cce8f9038c566e3f2caf6df925d6d3c1bba2 — целевая проверка forked Gate.
What changed: HEAD CARD-0083 больше не сообщает об ожидании ручного merge и указывает `main`.
Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` → PASS; `git merge-base --is-ancestor f2d9cce8f9038c566e3f2caf6df925d6d3c1bba2 HEAD` → PASS; CARD-0083 LOG records the target suite PASS.
One next action: не возвращать статус ожидания ручного merge для уже включённых проверок.

## LOG

### 2026-08-13 — Implement

Обновлён HEAD CARD-0083: устаревшие ветка и ожидание ручного merge заменены
фактическим состоянием `main`; добавлена проверяемая запись о результате.
