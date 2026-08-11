-- Specification is a documentation delivery stage.  Publish a new immutable
-- revision for enabled Specification workflows so the handoff gate receives a
-- committed, pushed artifact instead of a retained-worktree-only report.
INSERT INTO workflow_revisions(
    id, workflow_id, revision_number, request_key, request_digest,
    title, summary, instructions, created_at
)
SELECT
    'migration-023-specification-publishes-documents-' || workflow.id,
    workflow.id,
    revision.revision_number + 1,
    'migration:023:specification-publishes-documents:' || workflow.id,
    randomblob(32),
    revision.title,
    revision.summary,
    'Ты выполняешь только этап Specification. Не реализуй продуктовый код, не
меняй UI и не исправляй исходники приложения. Подготовь спецификацию в
`knowledge/specs/` и отдельную карточку
`knowledge/cards/CARD-0074-specification-publishes-documents.md`; область
должна содержать только документы, необходимые для этой спецификации.
Работай в назначенной рабочей ветке и не переключай её. Перед сдачей
выполни `git fetch origin main`, при необходимости `git rebase origin/main`,
затем проверь `git diff --name-only origin/main...HEAD` — diff должен быть
непустым и содержать только документы этой задачи. Обязательно выполни
commit с русским человеческим заголовком и
`git push -u origin HEAD`. Отчёт закончи отдельными строками:
`BRANCH: <имя назначенной ветки>`, `HEAD: <полный SHA последнего коммита>` и
`PUSHED: yes`. Без commit и push этап не считается завершённым.',
    CAST(strftime('%s', 'now') AS INTEGER) * 1000
FROM workflows AS workflow
JOIN workflow_revisions AS revision ON revision.id = workflow.current_revision_id
WHERE workflow.enabled = 1
  AND revision.title = 'Specification';

UPDATE workflows
SET current_revision_id = 'migration-023-specification-publishes-documents-' || id,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE enabled = 1
  AND id IN (
      SELECT workflow_id FROM workflow_revisions
      WHERE request_key LIKE 'migration:023:specification-publishes-documents:%'
  );
