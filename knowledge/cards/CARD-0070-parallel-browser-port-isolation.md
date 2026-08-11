# CARD-0070 — Параллельные browser-проверки получают изолированные адреса

## HEAD

- Implementation commit: отсутствует — стадия Specification не реализует код.
- Status: Specified — awaiting implementation.
- Specification: `knowledge/specs/parallel-browser-port-isolation.md`.
- What changes: каждый `just test-browser` получит собственный loopback-адрес
  и отдельные browser artifacts вместо общего порта `17437`.
- Evidence: текущие `web/playwright.config.ts`, `web/e2e/server.mjs` и
  `web/e2e/control-plane.spec.ts` используют один литерал `127.0.0.1:17437`.
- Open risk: handoff резерва порта в Node-запускаторе требует ограниченного
  retry при внешнем захвате; глобальный lock сознательно отклонён, чтобы не
  сериализовать четыре Verify.
- One next action: Implement выполнить спецификацию и записать реализационный
  коммит в карточку до её финального обновления.

## LOG

### 2026-08-11 — Specification

Выбран динамический run-scoped адрес: он проходит от запускатора в Playwright,
fixture-server, worker, poller и прямые API-контексты. План включает
межпроцессную регрессию двух одновременных запусков, измерение выбора адреса и
изоляцию каталогов evidence. Реализация на этой стадии намеренно отсутствует.
