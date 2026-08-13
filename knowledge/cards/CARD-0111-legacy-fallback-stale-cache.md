# CARD-0111: усилить legacy fallback и fixture stale-cache

## HEAD

Status: Implemented
Branch: `factory/d8a17c2c-94c-973bb42e-a68`
Implementation commit: 1a40e53674cc211b4f274b92c6bac4aeca98311f — Review блокирует невалидную identity и проверяет stale-cache через pinned SHA.
What changed: удалён synthetic legacy fallback через `branch_report`; добавлен тест, где cached `origin/main` устарел, а scope берётся от свежего remote base.
Evidence: `python3 -m unittest -q pilot.test_pilot.FreshDefaultBranchSnapshotTests.test_stale_cached_main_never_defines_review_scope` → OK; целевые legacy/fixture тесты → OK.
One next action: прогнать полный Pilot-набор на этапе Verify.

## LOG

### 2026-08-12 — Implement

Изменён `pilot/pilot.py`: Review теперь fail-closed для отсутствующей или невалидной repository identity и не вызывает legacy `branch_report` как authoritative fallback. В `pilot/test_pilot.py` добавлена stale-cache fixture с observer, клонированным до продвижения remote main, и проверкой pinned scope. Целевой тест и `git diff --check` зелёные; первый полный Pilot-набор выявил несовместимые старые seam-тесты, которые были обновлены в той же поставке.
