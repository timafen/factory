# Review всегда сравнивает со свежей основной веткой

## Цель и влияние на владельца

Устранить ложные REQUEST CHANGES и повторные раунды, возникающие из-за stale
`origin/main` в retained worktree. Для чистой ветки GitHub compare (11 файлов,
ahead_by=2) Review и Verify должны видеть ровно её фактический scope, а не 49
чужих файлов. Отчёт должен отличать дефект кода от ошибки review-инфраструктуры.

## Технический подход и реальные файлы

Работу начать от `origin/main`. В Review и Verify перед любым three-dot diff,
log, ancestry или empty-delivery judgement определить remote default branch
(`git remote get-url`/GitHub metadata согласно существующему source-access
контракту), fetch-нуть exact remote ref с pruning/force-safe обновлением и
сохранить immutable `base_sha` и `candidate_sha`. Все последующие команды
работают с SHA, не с локальным cached ref; оба SHA попадают в verdict/report.
Ошибку resolution/fetch трактовать как `BLOCKED`, не как чистый diff и не как
REQUEST CHANGES. GitHub compare может corroborate результат, но не заменяет
локально fetched SHAs. Worker-owned branch не переключать: использовать
отдельный read-only worktree/temporary ref или `git -C` текущего worktree.

Точки реализации и тестов:

- `pilot/pilot.py` — prompt/переходы Pipeline и обработка Review/Verify verdict;
  добавить общий resolver/snapshot helper и human-readable infrastructure
  reason.
- `pilot/test_pilot.py` — unit/regression fixture, включая stale local
  `origin/main`, advancing remote main, clean candidate, exact file scope,
  SHA recording, fetch failure/BLOCKED и branch preservation.
- `pilot/config.example.json` — source-of-truth mapping новых Review/Verify
  revision IDs/rollout notes, если текущая схема требует явного pinning.
- Live control plane (не репозиторный файл): immutable Workflow revisions
  через `/api/v1/workflows/{workflow_id}/revisions`, затем Pilot config
  `/opt/factory-data/pilot/config.json`; не менять существующие task snapshots.
  Развёртывание — штатным `fx factory release main` после безопасного smoke.

## Последовательный план

1. Зафиксировать текущую семантику source-access, default-branch resolution,
   Review/Verify prompt и verdict schema; сохранить обратную совместимость.
2. Реализовать fetch-and-pin helper с явной проверкой remote ref и SHA; внедрить
   его до всех сравнений/решений обеих стадий и запретить stale fallback.
3. Записывать base/candidate SHA, fetched ref и blocked reason в результат,
   сохранив worker branch и existing running tasks неизменными.
4. Добавить regression fixture: stale origin/main -> remote main advances ->
   clean candidate; old path демонстрирует false files, новый — exact scope.
5. Выпустить новые immutable Review/Verify revisions, обновить Pilot/new-task
   selection, выполнить live smoke; rollback pin описать и проверить.

## Критерии приёмки

- Обе стадии fetch-ят exact resolved default ref до любого diff/log/ancestry/
  empty decision и используют только fetched immutable SHAs.
- Verdict/report содержит оба SHA и различает application defect и stale-review
  infrastructure; GitHub compare лишь подтверждает локальный результат.
- Fetch или default resolution failure даёт BLOCKED; stale refs не рецензируются.
- Worker branch никогда не switch/reset; running tasks не мутируются.
- Regression fixture показывает старое false scope и новое exact scope.
- Live revisions обновлены безопасно, Pilot и новые tasks используют их; rollback
  к предыдущим revision_id документирован.

## Тест-план

Основная обязательная проверка: `python3 -m unittest pilot.test_pilot`.
Добавить изолированный git fixture с отдельным bare remote и два commits main:
  stale local base содержит лишний набор файлов, remote main продвинут, candidate
  чистый; assert old comparison lists false files, new comparison lists exact 11
  files and `ahead_by=2`. Отдельно проверить fetch/default failure => BLOCKED,
  SHA fields, no branch switch и unchanged task snapshot. Запустить существующие
  Pilot tests и live smoke новых revisions без изменения running tasks.

## Риски и решения

- Force-push/default-branch race: fetch ref, resolve SHA и проверить candidate
  ancestry in one pinned operation; при несогласованности повторить или BLOCKED.
- Remote permissions/network outage: явный BLOCKED с причиной, без cached fallback.
- Retained worktree загрязнён: изолированный read-only comparison context.
- Live rollout ломает новые задачи: immutable revisions, staged smoke и pin rollback;
  старые tasks продолжают snapshots старых ревизий.
- GitHub API отличается от Git: локально fetched SHAs authoritative, API только
  corroboration.

## Карточка работы

`knowledge/cards/CARD-0087-review-uses-fresh-default-branch.md` — новая карточка,
номер проверен после CARD-0085 в `origin/main`; CARD-0086 зарезервирована.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл pilot/config.example.json
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot
