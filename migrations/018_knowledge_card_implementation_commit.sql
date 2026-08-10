-- Existing workflow instructions are data, not source files.  Publish a new
-- immutable revision for every live Review/Verify workflow so the corrected
-- card rule takes effect immediately after an upgrade.
INSERT INTO workflow_revisions(
    id, workflow_id, revision_number, request_key, request_digest,
    title, summary, instructions, created_at
)
SELECT
    'migration-018-implementation-commit-' || workflow.id,
    workflow.id,
    revision.revision_number + 1,
    'migration:018:implementation-commit:' || workflow.id,
    randomblob(32),
    revision.title,
    revision.summary,
    revision.instructions || '

Карточка знаний подтверждает реализацию только стабильной строкой `Implementation commit: <полный SHA> — <что реализовано>`. Это существующий коммит с кодом в данной ветке, сделанный до отдельного финального коммита карточки. Прежнее требование `Head commit = git HEAD` отменено: последующая документационная запись закономерно меняет HEAD и сама по себе не является причиной REQUEST CHANGES. Однако отсутствующий, выдуманный, не принадлежащий ветке или меняющий только knowledge/cards implementation commit — ошибка и должен вернуть работу.',
    CAST(strftime('%s', 'now') AS INTEGER) * 1000
FROM workflows AS workflow
JOIN workflow_revisions AS revision ON revision.id = workflow.current_revision_id
WHERE workflow.enabled = 1
  AND lower(revision.title) IN ('review', 'verify')
  AND revision.revision_number < 100;

UPDATE workflows
SET current_revision_id = 'migration-018-implementation-commit-' || id,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE enabled = 1
  AND current_revision_id IN (
      SELECT id FROM workflow_revisions
      WHERE request_key LIKE 'migration:018:implementation-commit:%'
  );
