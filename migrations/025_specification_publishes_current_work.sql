-- Persist the live Specification revision that binds documentation to the
-- current work instead of sending every work item to CARD-0074.
INSERT INTO workflow_revisions(
    id, workflow_id, revision_number, request_key, request_digest,
    title, summary, instructions, created_at
)
SELECT
    'migration-025-specification-publishes-current-work-' || workflow.id,
    workflow.id,
    revision.revision_number + 1,
    'migration:025:specification-publishes-current-work:' || workflow.id,
    randomblob(32),
    revision.title,
    revision.summary,
    'Ты выполняешь только этап Specification. Не реализуй продуктовый код, не
меняй UI и не исправляй исходники приложения. Подготовь спецификацию в
`knowledge/specs/` и отдельную карточку текущей работы. Если context содержит
строку `Card:` или путь `knowledge/cards/CARD-*.md`, используй именно эту
карточку. Если карточка не указана, создай для текущей работы отдельную карточку
с новым свободным номером. Никогда не используй фиксированную CARD-0074 как
универсальную карточку. Изменяй только документы этапа Specification,
необходимые для этой работы.
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
SET current_revision_id = 'migration-025-specification-publishes-current-work-' || id,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE enabled = 1
  AND id IN (
      SELECT workflow_id FROM workflow_revisions
      WHERE request_key LIKE 'migration:025:specification-publishes-current-work:%'
  );
