# CARD-0304 — Ежедневный PDF после чистого штатного выпуска

Implementation commit: 0f32220202798bded67ad69b41b55dc4526c842c — Playwright объявлен runtime-зависимостью отчётного рендерера; его сохранение между временной сборкой и работающим сервером этой работой ещё не реализовано.

## HEAD

- Status: SPECIFIED
- Branch: `factory/65071c1a-1e8-64842db5-b90`
- Owner outcome: штатный выпуск сам доставляет проверенный runtime Playwright для снимков и PDF; владельцу не нужно выполнять `npm install` в `/opt/factory`.
- Scope: durable Node runtime под управляемым `FACTORY_DATA_HOME`, явная передача его абсолютного `package.json` двум встроенным report-скриптам, обязательная подготовка до переключения служб и регрессии чистого выпуска.
- Non-goal: не менять экран «Отчёты», формат PDF, расписание отчёта, allowlist браузера или ослаблять Chromium sandbox.
- Specification: `knowledge/specs/daily-pdf-clean-release-runtime.md`.
- One next action: Implement по указанной спецификации.

## LOG

### 2026-08-15 — Triage / Specification

Текущий `fx-factory-release` выполняет `npm ci` только в `$work/src/web`, а затем
удаляет весь `$work`. Встроенные `render.mjs` и `capture.mjs` сначала ищут пакет
рядом с материализованным скриптом, затем через `process.cwd()/web/package.json`.
Это делает боевой PDF зависимым от вручную оставленного `node_modules` в
`/opt/factory/web`. Отдельный `install-server-browser.sh` также ставит зависимости
в переданный временный payload и текущий release driver его не вызывает.

Спецификация задаёт один управляемый runtime вне checkout, атомарную активацию
после smoke и точную передачу пути дочерним Node-процессам. Регрессии должны
воспроизвести пустой `/opt/factory`, удаление build-clone и создание PNG/PDF после
успешного штатного выпуска.

Текущее воспроизведение подтверждено без изменения продукта: из чистого checkout
`node --test web/report/report.test.mjs` останавливается на `ERR_MODULE_NOT_FOUND`
для `playwright`, тогда как изолированная проверка существующего browser installer
проходит. Это отделяет отсутствие доставленного Node runtime от Chromium sandbox.
