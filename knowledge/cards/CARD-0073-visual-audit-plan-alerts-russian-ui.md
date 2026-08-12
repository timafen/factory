# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/5ee79231-823-ec132af2-864`.
Implementation commit: 0579ce69eccea6d891668882d88689489e9909e4 — проверка единственности кнопки сохранения Settings.
- What changed: Settings E2E scoped к `.settings-page`; кнопка выбирается exact role/name без `.first()`.
- Evidence: pinned diff `main...candidate` меняет только эту карточку; Go-тесты и UI Vitest зелёные, TypeScript и lint проходят.
- One next action: передать на человеческое слияние.

## LOG

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Кандидат меняет только карточку | pinned `main...candidate` | только `knowledge/cards/CARD-0073-visual-audit-plan-alerts-russian-ui.md` |
| Settings падает при дубликате кнопки | pinned commit `0579ce69`, `web/e2e/control-plane.spec.ts` | `.settings-page` + exact role/name + `toHaveCount(1)` подтверждены |
| Регрессий в тестах нет | `go test -timeout 5m ./...`; `npx tsc -p tsconfig.app.json --noEmit`; `npm run lint`; `npm test -- --run` | PASS; 160 UI-тестов |

`just check` остановился на существующем `SA4000` в `internal/worker/attempt_lifecycle_test.go`, вне области карточки; остальные целевые проверки прошли.
