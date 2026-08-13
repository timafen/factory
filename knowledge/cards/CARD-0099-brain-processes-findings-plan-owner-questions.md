# CARD-0099 — Мозг сам разбирает находки в План

Implementation commit: 856310dca1702c26f3a61895f183d685d00ac588 — автоматические отчёты с находками сохраняются в Плане.

## HEAD

- Status: Specification — ready for implementation.
- Branch: `factory/996ca9ca-68b-1394fd5e-00e`.
- Specification: `knowledge/specs/brain-processes-findings-plan-owner-questions.md`.
- Owner impact: технические находки попадают в План, а вопрос приходит только
  когда действительно требуется решение владельца.
- One next action: реализовать проверяемые границы разбора и маршрутизации.

## LOG

### 2026-08-12 — Specification

Фактический Pilot уже сохраняет `НАХОДКА:` из успешных pipeline и Automation
отчётов через `collect_ideas` и показывает их в `/intake/plan`; `orchestrator_answer`
уже перечисляет владельческие причины эскалации. Спецификация расширяет контракт
на все terminal-result, устойчивый источник/дедупликацию и fail-closed техническую
деградацию: сбой мозга не становится ложным вопросом владельцу.

Реализация ограничена `pilot/pilot.py` и `pilot/test_pilot.py`; экран Plan,
control-plane API и схема данных не требуют изменений.
