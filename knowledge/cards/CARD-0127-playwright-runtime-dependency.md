Implementation commit: будет создан на этапе Implement — `playwright` станет прямой production-зависимостью генератора PDF.

# CARD-0127 — Runtime-зависимость Playwright для PDF-отчётов

## HEAD

- Status: Specification ready for implementation.
- Branch: `factory/5a21187b-526-78e260f2-696`.
- Specification: `knowledge/specs/playwright-runtime-dependency.md`.
- What is planned: прямой импорт `playwright` в генераторе PDF будет объявлен
  runtime-зависимостью и подтверждён чистой production-установкой.
- Scope: `web/package.json`, `web/package-lock.json`,
  `web/report/report.test.mjs`.

## LOG

### 2026-08-14 — Specification

Подтверждён разрыв: `web/report/render.mjs` импортирует `playwright`, но
`web/package.json` содержит только dev-зависимость `@playwright/test`, тогда как
production audit устанавливает `npm ci --omit=dev`. Выбран минимальный план:
добавить только runtime-пакет `playwright`, сохранить test runner в dev-разделе,
обновить lockfile и зафиксировать чистый import без dev-зависимостей. Код на
этапе Specification не менялся; implementation commit появится в следующем
этапе до обновления этой карточки.
