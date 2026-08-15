Implementation commit: 58949df1a96ae2a8b47ffed94f734fa21e0fa08b — исправлены две фикстуры AdaptivePollingTests, а полный набор Pilot добавлен в обязательные параллельные CI-ворота.

## HEAD

Status: Implemented and tested; ready for review.
Branch: `factory/941de262-eaf-31167ccb-cd2`.
What changed: `dashboard_slow` изолирован в обеих адаптивных фикстурах; CI запускает `python3 -m unittest pilot.test_pilot` параллельно с Linux и macOS и требует успеха Pilot в итоговом `check`.
Evidence: `AdaptivePollingTests` — 24/24; `pilot.test_pilot` — 289/289, 13 skipped; `git diff --check` — PASS.
One next action: провести Review по опубликованному SHA кандида.

## LOG

### 2026-08-14 — Implement

Исправлены две красные проверки `AdaptivePollingTests`; полный Python-набор Pilot стал отдельным обязательным CI-job. На финальном SHA реализации прошли 24/24 целевых и 289/289 полных тестов Pilot (13 skipped).
