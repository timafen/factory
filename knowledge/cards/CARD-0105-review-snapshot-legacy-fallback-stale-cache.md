# CARD-0105: усилить legacy fallback и fixture stale-cache

Implementation commit: ac3ef660715a20f7b50711a57f7d787f63883598 — введён authoritative snapshot Review и базовая stale-cache регрессия; этап Specification фиксирует последующее усиление и не меняет продуктовый код.

Status: Specification — готово к реализации.
Branch: `factory/e9493554-af3-9c2811e6-0cb`
Scope: `pilot/pilot.py`, `pilot/test_pilot.py`.

## Контракт

Review не принимает неполную или невалидную repository identity как источник
сравнения. Такой вызов завершается `BLOCKED: review infrastructure` до
`branch_report`, cap-rescue и любого verdict. Валидный вызов сравнивает только
прикреплённые `base_sha...candidate_sha`; cached `origin/main` не является
authoritative.

Fixture обязана клонировать observer до продвижения remote `main`. Поэтому
cached ref остаётся старым, а pinned fetch получает новый default branch и
показывает точный scope. Worker-owned branch не переключается и не сбрасывается.

## Передача в реализацию

- Изменить `pilot/pilot.py` и `pilot/test_pilot.py` согласно
  `knowledge/specs/review-snapshot-legacy-fallback-stale-cache.md`.
- Не менять `knowledge/cards/CARD-0087-review-uses-fresh-default-branch.md`
  и `knowledge/cards/CARD-0090-verify-refreshes-remote-snapshot.md`.
- После реализации повторить целевую проверку, полный Pilot-набор и
  `git diff --check`.

## Проверяемые обещания

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.FreshDefaultBranchSnapshotTests.test_stale_cached_main_never_defines_review_scope
