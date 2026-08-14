# CARD-0127: тесты Pilot как ворота выкатывания

## HEAD

Status: Specified — awaiting Implement
Implementation commit: не создан — этап Specification не меняет код; реализационный коммит должен предшествовать следующему обновлению карточки.
What changed: определены детерминированные обновления двух AdaptivePollingTests и обязательный параллельный Python gate для локального выката.
Evidence: спецификация `knowledge/specs/pilot-tests-release-gate.md` сопоставляет каждый критерий с фактическими `pilot/test_pilot.py`, `ops/fx-factory-release` и `ops/test-fx-factory-release.sh`.
One next action: реализовать только указанные тесты, release gate и shell-фикстуру.

## LOG

### 2026-08-13 — Specification

Зафиксирована поставка без product-кода: обе красные проверки должны выдавать
достаточную детерминированную последовательность часов для live-status и
`record_poll_hint`; полный `python3 -m unittest pilot.test_pilot` становится
именованной параллельной группой перед сборкой. Shell-фикстура обязана доказать
его pre-build запуск, отмену остальных групп при отказе и неизменность
installation/services без конфигурационного обхода.
