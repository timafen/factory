# CARD-0045 — Граница переиспользования Bernstein в Factory

## HEAD

- Status: Specification — готова к решению владельца.
- Branch: `factory/b189d8fe-629-235403a3-37c`.
- Head commit: `53907ab` (`Определить границу переиспользования Bernstein в Factory`).
- Specification: `knowledge/specs/bernstein-reuse-evaluation.md`.
- What changed: сопоставлены Factory и Bernstein 3.13.0; предложен только
  выключенный по умолчанию PoC Bernstein как подчинённого движка одного Attempt.
- Evidence: спецификация фиксирует снимок upstream, матрицу владения, восемь
  проверяемых критериев, условия продолжения и отказа; проверки структуры и
  `git diff --check` прошли.
- One next action: владельцу решить, разрешать ли отдельный offline PoC адаптера.

## LOG

### 2026-08-09 — Specification

На свежем `origin/main` изучены текущая и целевая архитектуры Factory, а также
исходный снимок Bernstein 3.13.0 `f6bc3b43`. За Factory сохранены admission,
durable state, fleet routing, permissions, provider actions и UI. Для Bernstein
ограничен PoC внутреннего DAG, CLI adapters, worktree, gates и evidence внутри
одной попытки; перенос исходников и второй источник истины отвергнуты. Заданы
восемь критериев проверки и явные условия остановки эксперимента.

### 2026-08-09 — Implement

Продуктовый код намеренно не менялся: утверждённый владельцем результат этого
этапа — новая спецификация сравнения. Проверки обязательных разделов, исходного
commit и лицензионной отметки прошли; трёхточечный diff содержит только карточку
и спецификацию, `git diff --check` не нашёл ошибок.
