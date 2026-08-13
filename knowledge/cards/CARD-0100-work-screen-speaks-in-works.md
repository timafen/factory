# CARD-0100 — Экран «Работа» говорит на языке работ

Implementation commit: c3f3a425e2d7e959079f09c33a99af8153c86a7a — зафиксирован проверяемый контракт реализации; продуктовый код на этапе Specification не изменялся.

## HEAD

- Status: Specification complete — ready for Implement + Test.
- Specification: `knowledge/specs/work-screen-speaks-in-works.md`.
- Owner impact: одноимённые работы перестанут сливаться, а разные виды
  ожидания будут подписаны по смыслу.
- Scope: только уже существующие задачи и их `work_id`; pre-task реестр не
  создаётся.
- Implementation files: `web/src/types.ts`, `web/src/Work.tsx`,
  `web/src/Work.test.ts`, `web/src/WorkView.test.tsx`,
  `web/src/App.tsx`, `web/src/App.test.tsx`.
- Required check: `npm --prefix web test -- --run src/Work.test.ts src/WorkView.test.tsx src/App.test.tsx`.
- One next action: реализовать спецификацию и заменить эту строку
  Implementation commit на полный SHA продуктового коммита.

## LOG

### 2026-08-12 — Specification

Control plane уже возвращает устойчивый `work_id`, но web-тип его не
описывает, а экран объединяет историю по очищенному заголовку. Определено:
группировать по `work_id` с title fallback для legacy-задач, держать UI-state
по тому же identity, а владельцу показывать название, не технический id.

Три смысла «очереди» разведены на ожидание исполнителя текущим этапом,
подготовку следующего этапа Factory и техническое ожидание запуска отдельной
задачи на доске этапов. Основной экран называется «Работа», служебный —
«Исполнители».

Осознанное решение владельца: работа без единой задачи в текущую поставку не
входит. Отдельный durable API/реестр ради pre-task состояния не создаётся,
поскольку такая работа сейчас не возникает как доступная экрану сущность.

Triage-ветка `factory/e993352d-43d-c2a304bc-244` отсутствовала в origin на
момент Specification; её отчёт передан в контексте и подтверждал отсутствие
изменений, поэтому спецификация построена по свежему `origin/main` и
фактическим контрактам кода.
