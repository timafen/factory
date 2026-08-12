# Review всегда сравнивает со свежей основной веткой

## Цель и влияние на владельца

Устранить ложные REQUEST CHANGES и повторные раунды, возникающие из-за stale
`origin/main` в retained worktree. Review и Verify должны видеть ровно
фактический scope опубликованной ветки, а не файлы, пришедшие в основную ветку
после её создания. Отчёт должен отличать дефект кода от ошибки
review-инфраструктуры, чтобы владелец не получал ложный возврат на доработку.

## Технический подход и реальные файлы

Работу начать от `origin/main`. В `fresh_branch_snapshot` перед любым
three-dot diff, log, ancestry или решением о пустой поставке определить
default branch именно у remote через `git ls-remote --symref <url> HEAD`.
В новом временном Git-репозитории получить и принудительно закрепить ref
основной и кандидатной веток, затем записать immutable `base_sha`,
`candidate_sha` и `merge_base_sha`. Scope кандидата считать только как
`<merge_base_sha>...<candidate_sha>`: это сохраняет корректный diff, если
основная ветка успела продвинуться после публикации кандидата.

`review_gate` использует такой snapshot до подготовки контекста Review; Verify
получает те же обязательные правила через общий stage prompt. Ошибку remote
resolution, fetch или pin трактовать как `BLOCKED: review infrastructure`, не
как чистый diff и не как REQUEST CHANGES. Worker-owned checkout не изменять:
snapshot существует только во временном репозитории. GitHub compare допустим
только как дополнительное подтверждение, но не заменяет pinned SHA.

Точки реализации и тестов:

- `pilot/pilot.py` — `_default_branch`, `fresh_branch_snapshot` и `review_gate`:
  isolated fetch/pin, классификация продвинувшейся базы и понятный BLOCKED
  verdict. Общие правила для Review/Verify заданы в pipeline instructions.
- `pilot/test_pilot.py` — `FreshDefaultBranchSnapshotTests`: реальный bare
  remote, advancing `main`, точный scope кандидата, SHA fields, BLOCKED при
  ошибке и сохранение рабочей ветки наблюдателя.

`pilot/config.example.json` и live Workflow revisions не входят в эту работу:
свежесть базы обеспечивается runtime helper, а не конфигурационным pinning.

## Последовательный план

1. Зафиксировать текущую семантику source-access, Review/Verify prompt и
   verdict schema.
2. Реализовать isolated fetch-and-pin helper с remote default-branch discovery
   до всех сравнений и без fallback на cached refs.
3. Передавать в Review pinned SHA, merge-base, список файлов и BLOCKED reason,
   не меняя checkout воркера и существующие task snapshots.
4. Добавить regression fixture: remote main advances после публикации чистого
   кандидата; scope кандидата остаётся точным и наблюдатель остаётся на ветке.
5. Проверить focused regression и существующий Pilot suite; при rollout
   опубликовать immutable revision штатным выпуском, не мутируя running tasks.

## Критерии приёмки

- Review и Verify получают remote default ref до любого diff/log/ancestry/
  empty decision и используют только fetched immutable SHAs.
- Verdict/report содержит оба SHA и различает application defect и stale-review
  infrastructure; GitHub compare лишь подтверждает локальный результат.
- Fetch или default resolution failure даёт BLOCKED; stale refs не рецензируются.
- Worker branch никогда не switch/reset; running tasks не мутируются.
- Regression fixture доказывает exact scope, продвинувшуюся основную ветку и
  отсутствие смены ветки у наблюдателя.
- Если требуется rollout, новые immutable revisions выпускаются безопасно;
  running tasks сохраняют свои snapshots, rollback — возврат pin на прежнюю
  revision.

## Тест-план

Обязательная проверка: `python3 -m unittest
pilot.test_pilot.FreshDefaultBranchSnapshotTests`.
Изолированный fixture с bare remote создаёт кандидата из двух коммитов, затем
продвигает `main` чужим файлом. Проверить exact 11 файлов и `ahead_by=2`,
поля SHA, fetch/default failure => BLOCKED и неизменность ветки observer.
Дополнительно запустить полный существующий Pilot suite; live smoke новых
revisions нужен только при отдельном rollout.

## Риски и решения

- Force-push/default-branch race: fetch ref и pin SHA в одной isolated операции;
  при несогласованности вернуть BLOCKED, не использовать cached fallback.
- Remote permissions/network outage: явный BLOCKED с причиной, без cached fallback.
- Retained worktree загрязнён: изолированный read-only comparison context.
- Live rollout ломает новые задачи: immutable revisions, staged smoke и pin rollback;
  старые tasks продолжают snapshots старых ревизий.
- GitHub API отличается от Git: локально fetched SHAs authoritative, API только
  corroboration.

## Карточка работы

`knowledge/cards/CARD-0087-review-uses-fresh-default-branch.md` — закреплённая
карточка текущей работы; продолжает её исходную запись реализации.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests
