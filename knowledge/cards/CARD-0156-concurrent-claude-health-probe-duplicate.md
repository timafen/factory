# CARD-0156 — Закрыть повтор исправления Claude health-probe

Implementation commit: 9af274d80462f6b10c4a95392a65e5022795a2e7 — конкурентные Claude health-probe ограниченно ждут занятую одинаковую команду в рамках прежнего timeout.

## HEAD

- Status: Closed — Duplicate of CARD-0098; следующие продуктовые стадии не
  запускать.
- Branch: `factory/ed460ccf-c53-9340b60a-088`.
- Delivered by: PR #209 «конкурентные Claude health-probe ждут занятую
  команду», уже в `main`.
- Specification:
  `knowledge/specs/concurrent-claude-health-probe-duplicate-closeout.md`.
- What changed now: продуктовый код и CARD-0098 не менялись; текущая работа
  только документирует утверждённое владельцем закрытие дубликата.
- Evidence: implementation commit является предком свежего `origin/main`; четыре
  целевых worker-теста проходят с кодом 0.
- One next action: не запускать Implement, Review или Verify для этой работы;
  `SA4000`, устаревший статус CARD-0098 и browser-инфраструктуру учитывать
  отдельными находками.

## LOG

### 2026-08-13 — Specification

Владелец подтвердил `CLOSE / DUPLICATE`: CARD-0098 уже реализована и влита через
PR #209. Свежий `main` содержит bounded retry только для health-probe и целевые
регрессии; повторное изменение worker не требуется. Текущая карточка отделяет
закрытие дубликата от прежнего `SA4000`, редакционного состояния CARD-0098 и
недоступности browser suite, чтобы эти долги не перезапустили продуктовую работу.
