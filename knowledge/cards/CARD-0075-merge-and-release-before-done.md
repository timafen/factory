# CARD-0075 — Готовность работы подтверждается выпуском

## HEAD

- Status: Specification ready — ожидает реализации.
- Branch: `factory/99bcdebc-90b-936894ed-9cf`.
- Specification: `knowledge/specs/merge-and-release-before-done.md`.
- What changes: финальный PASS, переход эпика и уведомление владельцу будут
  возникать после подтверждённого успешного выпуска, а не сразу после merge.
- Evidence: спецификация сопоставлена с текущими `pipeline_watch`,
  `deploy_after_merge`, `poll_post_merge_deploys`, восстановлением эпиков и
  статусом terminal Verify в UI.
- Next action: Implement выполняет план из спецификации и дописывает сюда
  реализационный commit до финального коммита карточки.

## LOG

### 2026-08-11 — Specification

В `pipeline_watch` финальный PASS и сообщение «Задача выполнена» выдаются
сразу после `gh_merge`, а `deploy_after_merge` только резервирует фоновый
процесс. `poll_post_merge_deploys` знает код выпуска, но не связан с Verify
задачей; `advance_epics` принимает merge journal как окончательный receipt.

Выбран малый устойчивый контракт: сохранить ожидание поставки с task id и
минимальным поколением release, завершать его только после `rc=0`, а `rc=8`
переносить на retry. UI terminal Verify получает явное ожидание вместо
ошибочного «работа завершена». Новый контракт не блокирует цикл Pilot и не
изменяет команды штатного выпуска.
