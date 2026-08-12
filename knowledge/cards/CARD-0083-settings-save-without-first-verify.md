# CARD-0083 — Проверка кнопки сохранения настроек без `.first()`

Implementation commit: 2891a9046192c7164a76736094be9b686d9d0e62 — E2E сценарий сохраняет настройки пилота через русскую кнопку.

## HEAD

Status: BLOCKED: проверка кнопки сохранения настроек всё ещё выбирает элемент через `.first()`.
Branch: factory/421c71cf-9b7-1c860b02-11d.
Implementation commit: 2891a9046192c7164a76736094be9b686d9d0e62.
Evidence summary: полный browser-набор прошёл 22/22, однако `web/e2e/control-plane.spec.ts` содержит `getByRole(...).first().click()` для «Сохранить настройки», а экран рендерит две одноимённые адаптивные кнопки.
Next action: вернуть задачу на исправление — задать устойчивый локатор без `.first()` и подтвердить его целевой E2E-проверкой.

## LOG

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Кнопка сохранения проверяется без `.first()` | `grep -n 'Сохранить настройки.*first' web/e2e/control-plane.spec.ts` | BLOCKED: строка 1502 вызывает `.first().click()`. |
| Сохранение настроек выполняется в реальном браузере | `cd web && npm run test:browser` | PASS: 22 passed; сценарий `edits pilot settings from the Settings screen` выполнил PUT и сохранил значение после перезагрузки. |
| Сборка и полный общий набор | `just check` после `cd web && npm ci` | FAIL вне области: `TestLostClaimAndCompletionResponsesAreIdempotent` и `TestTimeoutStopsIgnoringProcessGroup` в `internal/worker`; Go-проверки до `go test` прошли. |
| Нет артефактов сборки и проблем патча | `git diff --check origin/main...HEAD`; `git status --short` | PASS: ошибок пробелов и незакоммиченных артефактов нет. |
